import abc
import time
import logging

logger = logging.getLogger(__name__)

class Job(object):
    def __init__(self, command, memory, time, name=None, output=None, error=None, parent=None):
        self.name = name
        self.command = command
        self.memory = memory
        self.time = time
        self.parent = parent
        self.output = output
        self.error = error
        # these will be set by an Executor object
        self.pid = None
        self.returncode = None
        self.active = None

class JobArray(object):
    def __init__(self, executor, cancel_on_fail=False):
        self.E = executor
        self.cancel_on_fail = cancel_on_fail
        self.array = list()
        self.running = dict() 
        self.complete = dict()
        self.failed = dict()
        self.polling_interval = 10
    
    def add(self, job):
        self.array.append(job)

    def submit(self):
        for job in self.array:
            self.E.submit(job)
            self.running[job.pid] = job

    def update(self):
        self.E.update_many(self.running.values())
        for pid in list(self.running):
            job = self.running[pid]
            if job.returncode == None:
                continue
            elif job.returncode == 0:
                self.complete[pid] = job
                del self.running[pid]
            elif job.returncode > 0:
                logger.debug('job %s returncode is %s', job.pid, job.returncode)
                self.failed[pid] = job
                del self.running[pid]

    def wait(self, wait=False):
        while 1:
            self.update()
            # if any jobs have failed and self.cancel_on_fail=True, cancel remaining jobs
            if len(self.failed) > 0 and self.cancel_on_fail:
                self.cancel(wait)
                return
            if len(self.running) == 0:
                return
            time.sleep(self.polling_interval)

    def cancel(self, wait=False):
        for job in self.running.values():
            self.E.cancel(job, wait=wait)

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

