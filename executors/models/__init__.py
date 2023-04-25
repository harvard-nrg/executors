import abc
import time
import logging
import executors.commons as commons

logger = logging.getLogger(__name__)

class Job(object):
    def __init__(self, command, memory, time, cpus=1, nodes=1, gpus=None, name=None, output=None, error=None, parent=None):
        self.name = name
        self.command = command
        self.memory = memory
        self.time = time
        self.parent = parent
        self.output = output
        self.error = error
        self.cpus = cpus
        self.gpus = gpus
        self.nodes = nodes
        # these fields are managed by an Executor
        self.pid = None
        self.returncode = None
        self.active = None

class JobArray(object):
    def __init__(self, executor, cancel_on_fail=False):
        '''
        :param executor: Executor instance
        :type executor: :mod:`executors.models.AbstractExecutor`
        :param cancel_on_fail: Cancel remaining jobs if any job fails
        :type cancel_on_fail: bool
        '''
        self.E = executor
        self.cancel_on_fail = cancel_on_fail
        self.array = list()
        self.running = dict() 
        self.complete = dict()
        self.failed = dict()
        self.active = 0
        self.inactive = 0
    
    def add(self, job):
        '''
        Add a job object to this job array.

        :param job: Job object
        :type job: :mod:`executors.models.Job`
        '''
        self.array.append(job)

    def submit(self, limit=None, delay=None):
        '''
        Submit the job array. To rate limit the number of jobs running 
        concurrently, use the limit parameter. To inject an artificial 
        delay between job submissions, use the delay parameter.

        Setting limit=None will submit all jobs and this method will return 
        immediately. You are responsible for calling JobArray.wait if you want 
        a blocking call. Providing a limit parameter will turn this method into 
        a blocking call since it needs to continuously monitor running jobs.

        :param limit: Limit the number of jobs running concurrently.
        :type limit: int
        :param delay: Wait N seconds between each job submission.
        :type delay: int
        '''
        if not limit:
            limit = len(self.array)
        cancel = False
        for job in self.array:
            submitted = False
            while not submitted:
                if len(self.running) < limit:
                    self.E.submit(job)
                    self.running[job.pid] = job
                    logger.debug('%s was submitted with pid %s', job.name, job.pid)
                    submitted = True
                    if delay:
                        time.sleep(delay)
                else:
                    self.update()
                    if len(self.failed) and self.cancel_on_fail:
                        logger.debug('cancelling gradual submission')
                        cancel = True
                        break
            if cancel:
                break
        if limit:
            self.wait()
    
    def update(self):
        '''
        Update all jobs in the job array.
        '''
        self.E.update_many(self.running.values())
        for pid in list(self.running):
            job = self.running[pid]
            if job.returncode == None:
                continue
            elif job.returncode == 0:
                logger.debug('job %s (%s) returncode is %s', job.pid, job.name, job.returncode)
                self.complete[pid] = job
                del self.running[pid]
            elif job.returncode > 0:
                logger.debug('job %s (%s) returncode is %s', job.pid, job.name, job.returncode)
                self.failed[pid] = job
                del self.running[pid]

    def wait(self, confirm_cancel=False):
        '''
        Wait for all jobs in the job array to complete. 

        If the job array is configured with cancel_on_fail=True, you can 
        pass confirm_cancel=True to wait for the executor to confirm that 
        all jobs have been cancelled. Without this, jobs will only be 
        signaled to cancel.

        :param confirm_cancel: Wait until jobs have been cancelled.
        :type confirm_cancel: bool
        '''
        while 1:
            self.update()
            # if any jobs have failed and self.cancel_on_fail=True, cancel remaining jobs
            if len(self.failed) > 0 and self.cancel_on_fail:
                self.cancel(confirm=confirm_cancel)
                return
            if len(self.running) == 0:
                return

    def cancel(self, confirm=False):
        '''
        Cancel all jobs in the job array. Pass confirm=True to wait for the 
        executor to confirm that all jobs have indeed been cancelled. Without 
        this parameter, jobs will only be signaled to cancel.

        :param confirm: Confirm that jobs have been cancelled
        :type confirm: bool
        '''
        for job in self.running.values():
            self.E.cancel(job, wait=confirm)

class AbstractExecutor(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def __init__(self, partition):
        pass

    @abc.abstractproperty
    def ACTIVE(self):
        raise NotImplementedError

    @abc.abstractproperty
    def INACTIVE(self):
        raise NotImplementedError

    @abc.abstractmethod
    def submit(self, job):
        pass

    @abc.abstractmethod
    def cancel(self, job):
        pass

    @abc.abstractmethod
    def update(self, job):
        pass

    @abc.abstractmethod
    def update_many(self, job):
        pass

