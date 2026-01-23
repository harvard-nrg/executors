import os
import re
import logging
import subprocess as sp
from executors.commons import which
from executors.models import AbstractExecutor
from executors.exceptions import ExecutorNotFound, CommandNotFound, TimeoutError
from ratelimit import limits, sleep_and_retry

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
        if which('qsub'):
            return True
        return False

    def submit(self, job):
        prefix = '{0}-%j'.format(job.name) if job.name else '%j'
        if not job.output:
            job.output = os.path.expanduser('~/{0}.out'.format(prefix))
        if not job.error:
            job.error = os.path.expanduser('~/{0}.err'.format(prefix))
        command = job.command
        if isinstance(command, list):
            command = sp.list2cmdline(command)
        if not which('qsub'):
            raise CommandNotFound('qsub')

        cmd = [
            'qsub',
            '-q', self.partition,
            '-d', os.getcwd()
        ]
        cmd.extend(self._default_args)
        cmd.extend(self._arguments(job))
        job_script = f'#!/bin/bash\n{command}'
        logger.debug(sp.list2cmdline(cmd))
        output = sp.check_output(
            cmd,
            stderr=sp.STDOUT,
            input=job_script.encode(),
        ).decode().strip()
        pid = re.search(r'^(\d+)', output).group(0)
        job.pid = pid
        self._alter_logs(job)
        logger.debug('parsed job id %s', pid)

    def _alter_logs(self, job):
        pid = job.pid
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
        try:
            output = self.qstat(job)
        except QstatUnknownJobError as e:
            job.active = False
            job.returncode = 1
            return
        job_state = re.search(r'job_state = (.*)', output).group(1)
        exit_status = re.search(r'exit_status = (.*)', output)
        if not exit_status:
            exit_status = -1
        else:
            exit_status = exit_status.group(1)
        output_path = re.search(r'Output_Path = (.*)', output).group(1)
        error_path = re.search(r'Error_Path = (.*)', output).group(1)
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
            if e.returncode == 170:
                logger.debug('job %s is in a completed state and cannot be cancelled', job.pid)
                pass
            elif e.returncode == 153:
                logger.debug('job %s is unknown and cannot be cancelled', job.pid)
                pass
            else:
                raise e

    @sleep_and_retry
    @limits(calls=5, period=20)
    def qstat(self, job):
        if not which('qstat'):
            raise CommandNotFound('qstat')
        cmd = [
            'qstat',
            '-f',
            job.pid
        ]
        logger.debug(cmd)
        try:
            output = sp.check_output(cmd)
        except sp.CalledProcessError as e:
            if e.returncode == 153:
                logger.debug('job %s is unknown to the scheduler', job.pid)
                raise QstatUnknownJobError(job)
            else:
                raise e
        return output.decode()

    def _parse_mem_value(self, s):
        try:
            match = re.match(r'^(\d+)(K|KB|M|MB|G|GB|T|TB)$', s)
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
            arguments.extend(['-o', os.path.expanduser(job.output)])
        if hasattr(job, 'error') and job.error:
            arguments.extend(['-e', os.path.expanduser(job.error)])
        if hasattr(job, 'parent') and job.parent:
            arguments.extend(['-W', 'depend=afterok:{0}'.format(job.parent.pid)])
        if hasattr(job, 'name') and job.name:
            arguments.extend(['-N', job.name])
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

class QstatUnknownJobError(QstatError):
    pass
