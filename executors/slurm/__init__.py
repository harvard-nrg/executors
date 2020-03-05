import os
import io
import six
import csv
import time
import logging
import subprocess as sp
from executors.commons import which
from executors.models import AbstractExecutor
from executors.exceptions import ExecutorNotFound, CommandNotFound, TimeoutError

logger = logging.getLogger('slurm')

class Executor(AbstractExecutor):
    ACTIVE = (
        'PENDING',
        'CONFIGURING',
        'RUNNING',
        'RESIZING',
        'SUSPENDED',
        'COMPLETING'
    )
    INACTIVE = (
        'COMPLETED',
        'CANCELLED',
        'FAILED',
        'OUT_OF_MEMORY', 
        'NODE_FAIL',
        'PREEMPTED', 
        'TIMEOUT'
    )

    def __init__(self, partition, **kwargs):
        if not self.available():
            raise SlurmNotFound()
        self.partition = partition
        self.polling_interval = 5
        self.timeout = 60
        self.args = self.translate(kwargs)

    def translate(self, kwargs):
        args = list()
        for k,v in iter(kwargs.items()):
            if k == 'nodelist':
                if not isinstance(v, list):
                    raise SbatchError('nodelist argument must be a list')
                args.extend([
                    '--nodelist', ','.join(v)
                ])
            elif k == 'exclude':
                if not isinstance(v, list):
                    raise SbatchError('nodelist argument must be a list')
                args.extend([
                    '--exclude', ','.join(v)
                ])
            else:
                logger.warn('unrecognized argument "%s"', k)
        return args

    @staticmethod
    def available():
        if which('sbatch'):
            return True
        return False

    def submit(self, job):
        command = job.command
        if isinstance(command, list):
            command = sp.list2cmdline(command)
        if not which('sbatch'):
            raise CommandNotFound('sbatch')
        cmd = [
            'sbatch',
            '--parsable',
            '--partition', self.partition
        ]
        cmd.extend(self.args)
        cmd.extend(self._arguments(job))
        cmd.extend([
            '--wrap', command
        ])
        logger.debug(cmd)
        pid =  sp.check_output(cmd).strip().decode()
        job.pid = pid

    def cancel(self, job, wait=False):
        job_id = job.pid + '.batch'
        if not wait:
            self._cancel_async(job.pid)
            return
        # cancel job and wait for the job to be registered as cancelled
        self._cancel_async(job.pid)
        logger.debug('waiting for job %s to be registered as CANCELLED', job_id)
        tic = time.time()
        while 1:
            self.update(job)
            if not job.active:
                break
            if time.time() - tic > self.timeout:
                raise TimeoutError('exceeded wait time {0}s for job {1}'.format(self.timeout, job_id))
            time.sleep(self.polling_interval)

    def _cancel_async(self, job_id):
        if not which('scancel'):
            raise CommandNotFound('scancel')
        cmd = [
            'scancel',
            job_id
        ]
        logger.debug(cmd)
        sp.check_output(cmd)

    def update(self, job, wait=False):
        # run sacct
        rows = self.sacct(job, wait=wait)
        # we should only have one row at this point
        if len(rows) == 0:
            return rows
        elif len(rows) > 1:
            raise SacctError('more rows than expected after parsing sacct output: {0}'.format(rows))
        row = rows.pop()
        job_state = row['State']
        job_code,sbatch_code = row['ExitCode'].split(':')
        # assume the return code is the greater of the two
        exit_status = max([int(sbatch_code), int(job_code)])
        logger.debug('pid {0} is in "{1}" state'.format(job.pid, job_state))
        if job_state in Executor.ACTIVE:
            job.active = True
        elif job_state in Executor.INACTIVE:
            job.active = False
            job.returncode = int(exit_status)

    def update_many(self, jobs, wait=False):
        for job in jobs:
            self.update(job, wait=wait)

    def sacct(self, job, wait=False):
        job_id = job.pid + '.batch'
        # return sacct output immediately
        if not wait:
            return self._sacct_async(job_id)
        # wait for the job to appear in sacct or timeout
        logger.debug('waiting for job %s to appear in sacct', job_id)
        tic = time.time()
        while 1:
            rows = self._sacct_async(job_id)
            if rows:
                return rows
            if time.time() - tic > self.timeout:
                raise TimeoutError('exceeded wait time {0}s for job {1}'.format(self.timeout, job_id))
            time.sleep(self.polling_interval)

    def _sacct_async(self, job_id):
        '''
        Run sacct command on a job and serialize output
        '''
        # build the sacct command
        if not which('sacct'):
            raise CommandNotFound('sacct') 
        cmd = [
            'sacct',
            '--parsable2',
            '--delimiter', ',',
            '--brief',
            '--jobs',
            job_id
        ]
        # execute the sacct command, serialize, and return the result
        logger.debug(cmd)
        output = sp.check_output(cmd, universal_newlines=True).strip()
        output = csv.DictReader(io.StringIO(six.u(output)))
        return [row for row in output]

    def _arguments(self, job):
        arguments = list()
        if hasattr(job, 'name') and job.name:
            arguments.extend(['--job-name', job.name])
        if hasattr(job, 'memory') and job.memory:
            arguments.extend(['--mem', job.memory])
        if hasattr(job, 'output') and job.output:
            arguments.extend(['--output', os.path.expanduser(job.output)])
        if hasattr(job, 'error') and job.error:
            arguments.extend(['--error', os.path.expanduser(job.error)])
        if hasattr(job, 'time') and job.time:
            arguments.extend(['--time', str(job.time)])
        if hasattr(job, 'parent') and job.parent:
            arguments.extend(['--dependency', 'afterok:{0}'.format(job.parent.pid)])
        return arguments

class SacctError(Exception):
    pass

class SlurmNotFound(ExecutorNotFound):
    pass

class SbatchError(Exception):
    pass
