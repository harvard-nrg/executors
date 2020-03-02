import os
import re
import logging
import paramiko
import getpass as gp
import subprocess as sp
import xml.etree.ElementTree as et
from executors.commons import which
from executors.models import AbstractExecutor
from executors.exceptions import ExecutorNotFound, CommandNotFound, TimeoutError

logger = logging.getLogger(__name__)

class Executor(AbstractExecutor):
    ACTIVE = (
        'Q',    # queued
        'R',    # running
        'H',    # held
        'E'     # exited
    )
    INACTIVE = (
        'C',    # complete
    )

    def __init__(self, partition, **kwargs):
        if not self.available():
            raise PBSubmitNotFound()
        self.partition = partition
        self.polling_interval = 5
        self.timeout = 60
        self._default_args = self.default_args(**kwargs)

    def default_args(self, **kwargs):
        args = list()
        for k,v in iter(kwargs.items()):
            if k == 'nodes':
                args.extend([
                    '-l', '+'.join(v)
                ])
            else:
                logger.warn('unrecognized Executor argument "%s"', k)
        return args

    @staticmethod
    def available():
        if which('pbsubmit'):
            return True
        return False

    def submit(self, job):
        command = job.command
        if isinstance(command, list):
            command = sp.list2cmdline(command)
        if not which('pbsubmit'):
            raise CommandNotFound('pbsubmit')
        cmd = [
            'pbsubmit',
            '-q', self.partition
        ]
        cmd.extend(self._arguments(job))
        cmd.extend([
            '-c', command
        ])
        logger.debug(sp.list2cmdline(cmd))
        output = sp.check_output(cmd, stderr=sp.STDOUT).decode('utf-8')
        output = output.strip().split('\n')
        pid = output[-1]
        job.pid = pid
        self._alter_logs(job) # insert pid into stdout and stderr files
        pbsjob = re.match('^Opening pbsjob_(\d+)', output[0]).groups(0)[0]
        job.pbsjob = pbsjob

    def _alter_logs(self, job):
        match = re.match('^(\d+)\.', job.pid)
        pid = match.group(1)        
        qalter_args = list()
        if job.output and '%j' in job.output:
            output = job.output.replace('%j', pid)
            qalter_args.extend(['-o', os.path.expanduser(output)])
        if job.error and '%j' in job.error:
            error = job.error.replace('%j', pid)
            qalter_args.extend(['-e', os.path.expanduser(error)])
        if qalter_args:
            if not which('qalter'):
                raise CommandNotFound('qalter')
            cmd = ['qalter'] + qalter_args + [pid]
            sp.check_output(cmd)

    def update(self, job, wait=False):
        xml = self.qstat(job)
        job_state = xml.findtext('.//job_state')
        exit_status = xml.findtext('.//exit_status')
        output_path = re.sub('^.*:', '', xml.findtext('.//Output_Path'))
        error_path = re.sub('^.*:', '', xml.findtext('.//Error_Path'))
        logger.debug('job {0} is in {1} state'.format(job.pid, job_state))
        if job_state in Executor.ACTIVE:
            job.active = True
        elif job_state in Executor.INACTIVE:
            job.active = False
            job.returncode = int(exit_status)

    def update_many(self, jobs, wait=False):
        for job in jobs:
            self.update(job, wait=wait)

    def cancel(self, job, wait=False):
        if not which('qdel'):
            raise CommandNotFound('qdel')
        cmd = [
            'qdel',
            job.pid
        ]
        try:
            logger.debug(cmd)
            sp.check_output(cmd, stderr=sp.PIPE)
        except sp.CalledProcessError as e:
            # qdel will return a 153 exit status if it tries to query the 
            # state of a Job ID that is already in a 'C' state, or a 170 
            # exit status if the Job ID is unknown. We should pass on either
            # of these states. A Job ID can become unknown only minutes after 
            # a job has entered the 'C' state.
            if e.returncode == 153:
                logger.debug('job %s is in a completed state and cannot be cancelled', job.pid)
                pass
            elif e.returncode == 170:
                logger.debug('job %s is unknown and cannot be cancelled', job.pid)
                pass
            else:
                raise e

    def qstat(self, job):
        if not which('qstat'):
            raise CommandNotFound('qstat')
        cmd = [
            'qstat',
            '-x',
            '-f',
            job.pid
        ]
        logger.debug(cmd)
        try:
            output = sp.check_output(cmd)
        except sp.CalledProcessError as e:
            if e.returncode == 170:
                logger.debug('job %s already in completed state, falling back to jobinfo', job.pid)
                output = self.jobinfo(job)
            elif e.returncode == 153:
                logger.debug('job %s unknown to the scheduler, falling back to jobinfo', job.pid)
                output = self.jobinfo(job)
            else:
                raise e
        return et.fromstring(output.strip())

    def jobinfo(self, job, node='launchpad'):
        cmd = [
            'jobinfo',
            job.pid
        ]
        username = gp.getuser()
        # ssh into head node to get job info
        logging.getLogger('paramiko').setLevel(logging.INFO)
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.connect(node)
        logger.debug('jobinfo command %s', cmd)
        _,stdout,_ = client.exec_command(sp.list2cmdline(cmd))
        stdout = stdout.read()
        client.close()
        # get job pid without domain  
        match = re.match('^(\d+)\.', job.pid)
        pid = match.group(1)
        # parse exit status
        stdout = stdout.decode('utf-8').strip().split('\n')
        match = re.match('^\s+Exit status: (-?\d+)$', stdout[-1])
        exit_status = match.group(1)
        logger.debug('discovered exit status: %s', exit_status)
        # build XML output similar to qstat -x
        root = et.Element('jobinfo')
        et.SubElement(root, 'job_state').text = 'C'
        et.SubElement(root, 'exit_status').text = exit_status
        et.SubElement(root, 'Output_Path').text = '/pbs/{0}/pbsjob_{1}.o{2}'.format(username, job.pbsjob, pid)
        et.SubElement(root, 'Error_Path').text = '/pbs/{0}/pbsjob_{1}.e{2}'.format(username, job.pbsjob, pid)
        return et.tostring(root)

    def _parse_mem_value(self, s):
        try:
            match = re.match('^(\d+)(K|KB|M|MB|G|GB|T|TB)$', s)
            size,unit = match.group(1),match.group(2)
        except:
            raise IndecipherableMemoryArgument(m)
        if unit in ('K', 'KB'):
            unit = 'kb'
        elif unit in ('M', 'MB'):
            unit = 'mb'
        elif unit in ('G', 'GB'):
            unit = 'gb'
        elif unit in ('T', 'TB'):
            unit = 'tb'
        memarg = size + unit
        logger.debug('translated memory argument %s', memarg)
        return size + unit

    def _arguments(self, job):
        arguments = list()
        qsub_opts = dict()
        if hasattr(job, 'output') and job.output:
            arguments.extend(['-O', os.path.expanduser(job.output)])
        if hasattr(job, 'error') and job.error:
            arguments.extend(['-E', os.path.expanduser(job.error)])
        if hasattr(job, 'parent') and job.parent:
            arguments.extend(['-W', 'depend=afterok:{0}'.format(job.parent.pid)])
        if hasattr(job, 'name') and job.name:
            arguments.extend(['-o', '-N {0}'.format(job.name)])
        if hasattr(job, 'memory') and job.memory:
            qsub_opts['vmem'] = self._parse_mem_value(job.memory)
        if hasattr(job, 'processors') and job.processors:
            qsub_opts['ppn'] = job.processors
        # build and append pass-through qsub options
        qsub_opts = 'nodes={NODES}:ppn={PPN},vmem={VMEM}'.format(
            NODES=qsub_opts.get('nodes', 1),
            PPN=qsub_opts.get('ppn', 1),
            VMEM=qsub_opts.get('vmem', '1gb')
        )
        arguments.extend(['-l', qsub_opts])
        return arguments

class PBSubmitNotFound(ExecutorNotFound):
    pass

class IndecipherableMemoryArgument(Exception):
    pass

class QstatError(Exception):
    pass
