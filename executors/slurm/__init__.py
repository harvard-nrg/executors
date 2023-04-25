import os
import io
import six
import csv
import time
import logging
import subprocess as sp
import executors.commons as commons
from executors.models import AbstractExecutor
from executors.exceptions import ExecutorNotFound, CommandNotFound, TimeoutError
from ratelimit import limits, sleep_and_retry

logger = logging.getLogger('slurm')

class Executor(AbstractExecutor):
    ACTIVE = (
        r'PENDING',
        r'CONFIGURING',
        r'RUNNING',
        r'RESIZING',
        r'SUSPENDED',
        r'COMPLETING'
    )
    INACTIVE = (
        r'COMPLETED',
        r'CANCELLED',
        r'CANCELLED by \d+',
        r'FAILED',
        r'OUT_OF_MEMORY', 
        r'NODE_FAIL',
        r'PREEMPTED', 
        r'TIMEOUT'
    )

    def __init__(self, partition, **kwargs):
        '''
        :param partition: Slurm partition
        :type partition: str
        :param nodelist: List of nodes to include (optional)
        :type nodelist: list
        :param exclude: Nodes to exclude (optional)
        :type nodelist: list
        :param reservation: Slurm reservation (optional)
        :type reservation: str
        '''
        if not self.available():
            raise SlurmNotFound()
        self.partition = partition
        self.poll_timeout = 60
        self.poll_delay = 1
        self.args = self._translate(kwargs)

    def _translate(self, kwargs):
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
            elif k == 'reservation':
                args.extend([
                    '--reservation', v
                ])
            else:
                logger.warn('unrecognized argument "%s"', k)
        return args

    @staticmethod
    def available():
        '''
        Check if Slurm is available on the system.
        '''
        if commons.which('sbatch'):
            return True
        return False

    def submit(self, job, **kwargs):
        '''
        Submit a job with sbatch. Pass wrap=False to disable wrapping the 
        command.

        :param job: Job object
        :type job: :mod:`executors.models.Job`
        :param wrap: Disable wrapping
        :type wrap: bool
        '''
        if not commons.which('sbatch'):
            raise CommandNotFound('sbatch')
        if not self.partition:
            raise SbatchError('no slurm partition was defined')
        cmd = [
            'sbatch',
            '--parsable',
            '--partition', self.partition
        ]
        cmd.extend(self.args)
        cmd.extend(self._arguments(job))
        wrap = kwargs.get('wrap', True)
        command = job.command
        if wrap:
            if isinstance(command, list):
                command = sp.list2cmdline(command)
            cmd.extend([
                '--wrap', command
            ])
        else:
            if isinstance(command, six.string_types):
                command = shlex.split(command)
            cmd.extend(command)
        logger.debug(cmd)
        pid =  sp.check_output(cmd).strip().decode()
        job.pid = pid

    def cancel(self, job, wait=False):
        '''
        Send scancel to a Slurm job. 

        Since cancelling a job in Slurm is inherently asyncronous, pass 
        wait=True to wait until the job state is updated.

        :param job: Job object
        :type job: :mod:`executors.models.Job`
        :param wait: Wait until the job state is updated
        :type wait: bool
        '''
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
            if time.time() - tic > self.poll_timeout:
                raise TimeoutError('exceeded wait time {0}s for job {1}'.format(self.poll_timeout, job_id))
            time.sleep(self.poll_delay)

    def _cancel_async(self, job_id):
        if not commons.which('scancel'):
            raise CommandNotFound('scancel')
        cmd = [
            'scancel',
            job_id
        ]
        logger.debug(cmd)
        sp.check_output(cmd)

    def update(self, job, wait=False):
        '''
        Update a single job state.

        Since querying job state in Slurm is inherently asyncronous, you must 
        pass wait=True to wait until the job state is updated.

        :param job: Job object
        :type job: :mod:`executors.models.Job`
        :param wait: Wait for job state to be updated
        :type wait: bool
        '''
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
        if commons.match(job_state, Executor.ACTIVE):
            job.active = True
        elif commons.match(job_state, Executor.INACTIVE):
            job.active = False
            job.returncode = int(exit_status)

    def update_many(self, jobs, wait=False):
        '''
        Update multiple job states.

        Since querying job state in Slurm is inherently asyncronous, you must 
        pass wait=True to wait until the job state is updated.

        :param jobs: List of :mod:`executors.models.Job` objects
        :type jobs: list
        :param wait: Wait for job state to be updated
        :type wait: bool
        '''
        # this should be implemented as one call
        for job in jobs:
            self.update(job, wait=wait)

    def sacct(self, job, wait=False):
        '''
        Run the sacct and return all rows. This method is rate limited to 
        5 calls every 20 seconds.

        Since sacct is inherently asyncronous, pass wait=True to wait until 
        the job state is updated.

        :param job: Job object
        :type job: :mod:`executors.models.Job`
        :param wait: Wait for job state to be updated
        :type wait: bool
        '''
        job_id = job.pid + '.batch'
        # return whatever sacct output is immediately
        if not wait:
            return self._sacct_async(job_id)
        # wait for the job to appear in sacct or timeout
        logger.debug('waiting for job %s to appear in sacct', job_id)
        tic = time.time()
        while 1:
            rows = self._sacct_async(job_id)
            if rows:
                return rows
            if time.time() - tic > self.poll_timeout:
                raise TimeoutError('exceeded wait time {0}s for job {1}'.format(self.poll_timeout, job_id))
            time.sleep(self.poll_delay)

    @sleep_and_retry
    @limits(calls=5, period=20)
    def _sacct_async(self, job_id):
        '''
        Run sacct command on a job and serialize output. This method is rate 
        limited to 5 calls every 20 seconds.

        :param job_id: Slurm job ID
        :type job_id: str
        :returns: List of sacct rows
        :rtype: list
        '''
        # build the sacct command
        if not commons.which('sacct'):
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
        if hasattr(job, 'cpus') and job.cpus:
            arguments.extend(['--ntasks', str(job.cpus)])
        if hasattr(job, 'gpus') and job.gpus:
            arguments.extend(['--gres', str(job.gpus)])
        if hasattr(job, 'nodes') and job.nodes:
            arguments.extend(['--nodes', str(job.nodes)])
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
