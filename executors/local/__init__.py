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

logger = logging.getLogger('local')

class Executor(AbstractExecutor):
    def __init__(self, **kwargs):
        self.ptab = dict()
        self.poll_timeout = 60
        self.poll_delay = 1

    @staticmethod
    def available():
        return True

    def submit(self, job, **kwargs):
        '''
        Submit a job locally. 

        :param job: Job object
        :type job: :mod:`executors.models.Job`
        '''
        cmd = job.command
        if isinstance(cmd, six.string_types):
            cmd = shlex.split(command)
        logger.debug(cmd)
        if job.error is None:
            job.error = job.output
        p = sp.Popen(
            cmd,
            stdout=open(job.output, 'w'),
            stderr=open(job.error, 'w')
        )
        job.pid = p.pid
        os.rename(job.output, job.output.replace('%j', str(job.pid)))
        os.rename(job.error, job.error.replace('%j', str(job.pid)))
        self.ptab[job.pid] = p

    def cancel(self, job, wait=False):
        '''
        Kill the process.

        Since killing a job is inherently asyncronous, pass 
        wait=True to wait until the job state is updated and 
        the process is confirmed dead.

        :param job: Job object
        :type job: :mod:`executors.models.Job`
        :param wait: Wait until the job state is updated
        :type wait: bool
        '''
        if not wait:
            self._cancel_async(job.pid)
            return
        # cancel job and wait for the job to be confirmed dead
        self._cancel_async(job.pid)
        logger.debug('waiting for job %s to be killed', job_id)
        tic = time.time()
        while 1:
            self.update(job)
            if not job.active:
                break
            if time.time() - tic > self.poll_timeout:
                raise TimeoutError('exceeded wait time {0}s for job {1}'.format(self.poll_timeout, job_id))
            time.sleep(self.poll_delay)

    def _cancel_async(self, pid):
        logger.debug('killing pid %s', pid)
        self.ptab[pid].kill()

    def update(self, job, wait=False):
        '''
        Update a single job state.

        :param job: Job object
        :type job: :mod:`executors.models.Job`
        :param wait: Wait for job state to be updated
        :type wait: bool
        '''
        p = self.ptab[job.pid]
        p.poll()
        job.active = True
        if p.returncode is not None:
            job.active = False
            job.returncode = p.returncode

    def update_many(self, jobs, wait=False):
        '''
        Update multiple job states.

        :param jobs: List of :mod:`executors.models.Job` objects
        :type jobs: list
        :param wait: Wait for job state to be updated
        :type wait: bool
        '''
        # this should be implemented as one call
        for job in jobs:
            self.update(job, wait=wait)
