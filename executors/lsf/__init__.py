import os
import re
import logging
import subprocess as sp
from executors.commons import which
from executors.models import AbstractExecutor
from executors.exceptions import ExecutorNotFound, CommandNotFound

logger = logging.getLogger(__name__)

class Executor(AbstractExecutor):
    ACTIVE = (
        'PEND',    # pending
        'WAIT',    # waiting
        'RUN',     # running
        'PSUSP',   # suspended while pending
        'USUSP',   # suspended while running
        'SSUSP'    # suspended for other reason
    )
    INACTIVE = (
        'DONE',    # completed successfully
        'EXIT',    # completed unsuccessfully
        'ZOMBI'    # zombie state
    )

    def __init__(self, partition, **kwargs):
        if not self.available():
            raise BsubNotFound()
        self.partition = partition
        self.polling_interval = 5
        self.timeout = 60
        self._default_args = self.default_args(**kwargs)

    def default_args(self, **kwargs):
        args = list()
        for k,v in iter(kwargs.items()):
            logger.warn('unrecognized executor argument "%s"', k)
        return args

    @staticmethod
    def available():
        if which('bsub'):
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
        if not which('bsub'):
            raise CommandNotFound('bsub')
        cmd = [
            'bsub',
            '-q', self.partition
        ]
        cmd.extend(self._default_args)
        cmd.extend(self._arguments(job))
        cmd.extend([
            command
        ])
        logger.debug(sp.list2cmdline(cmd))
        output = sp.check_output(cmd, stderr=sp.STDOUT).strip().decode()
        pid = re.search('^Job <(\d+)>', output).group(1)
        logger.debug('parsed job id %s', pid)
        job.pid = pid
 
    def update(self, job, wait=False):
        status = self.bjobs(job)
        job_state = status['job_state']
        exit_status = status['exit_status']
        output_path = status['output_path']
        error_path = status['error_path']
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
        if not which('bkill'):
            raise CommandNotFound('bkill')
        cmd = [
            'bkill',
            job.pid
        ]
        try:
            logger.debug(cmd)
            sp.check_output(cmd, stderr=sp.PIPE)
        except sp.CalledProcessError as e:
            # qdel will return a 255 exit status if it tries to query the 
            # state of a Job ID that is already in a 'C' state or if the 
            # Job ID is unknown. We should pass on either of these states
            if e.returncode == 255:
                logger.debug('job %s is in a completed state or unknown and cannot be cancelled', job.pid)
                pass
            raise e

    def bjobs(self, job):
        if not which('bjobs'):
            raise CommandNotFound('bjobs')
        cmd = [
            'bjobs',
            '-l',
            job.pid
        ]
        logger.debug(cmd)
        try:
            output = sp.check_output(cmd).strip().decode()
        except sp.CalledProcessError as e:
            raise e
        pid = re.match('Job <(\d+)>', output).group(1)
        job_state = re.search('Status <(\w+)>', output).group(1)
        exit_status = None
        if job_state in Executor.INACTIVE:
            exit_status = 0
            if job_state == 'EXIT':
                exit_status = re.search('Exited with exit code (\d+).', output).group(1)
        return {
            'pid': pid,
            'job_state': job_state,
            'exit_status': exit_status,
            'output_path': job.output,
            'error_path': job.error
        }

    def _parse_mem_value(self, s):
        try:
            match = re.match('^(\d+)(K|KB|M|MB|G|GB|T|TB)$', s)
            size,unit = match.group(1),match.group(2)
        except:
            raise IndecipherableMemoryArgument(m)
        if unit in ('K', 'KB'):
            memarg = .001 * int(size)
        elif unit in ('M', 'MB'):
            memarg = int(size)
        elif unit in ('G', 'GB'):
            memarg = int(size) * 1000
        elif unit in ('T', 'TB'):
            memarg = int(size) * 1000000
        if memarg < 1:
            memarg = 1
        logger.debug('translated memory argument %s', memarg)
        return str(int(memarg))

    def _arguments(self, job):
        arguments = list()
        qsub_opts = dict()
        if hasattr(job, 'output') and job.output:
            o = job.output.replace('%j', '%J')
            arguments.extend(['-o', os.path.expanduser(o)])
        if hasattr(job, 'error') and job.error:
            e = job.error.replace('%j', '%J')
            arguments.extend(['-e', os.path.expanduser(e)])
        if hasattr(job, 'name') and job.name:
            arguments.extend(['-J', job.name])
        if hasattr(job, 'memory') and job.memory:
            arguments.extend(['-M', self._parse_mem_value(job.memory)])
        if hasattr(job, 'parent') and job.parent:
            arguments.extend(['-w', 'done({0})'.format(job.parent.pid)])
        if hasattr(job, 'processors') and job.processors:
            arguments.extend(['-n', job.processors])
        return arguments

class BsubNotFound(ExecutorNotFound):
    pass

class IndecipherableMemoryArgument(Exception):
    pass
