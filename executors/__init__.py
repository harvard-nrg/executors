import os
import sys
import logging
import executors.lsf as lsf
import executors.slurm as slurm
import executors.local as local
import executors.pbsubmit as pbsubmit

logger = logging.getLogger(__name__)

def get(name, partition='default', **kwargs):
    if name == 'slurm':
        return slurm.Executor(partition, **kwargs)
    if name == 'pbsubmit':
        return pbsubmit.Executor(partition, **kwargs)
    if name == 'lsf':
        return lsf.Executor(partition, **kwargs)
    if name == 'local':
        return local.Executor(**kwargs)
    raise SchedulerNotFound(name)

def probe(partition, **kwargs):
    if slurm.Executor.available():
        logger.debug('detected slurm job scheduler')
        return slurm.Executor(partition, **kwargs)
    if pbsubmit.Executor.available():
        logger.debug('detected pbsubmit job scheduler')
        return pbsubmit.Executor(partition, **kwargs)
    if lsf.Executor.available():
        return lsf.Executor(partition, **kwargs)
    logger.debug('no schedulers detected, so returning a local executor')
    return local.Executor(**kwargs)

def which(x):
    for p in os.environ.get('PATH').split(os.pathsep):
        p = os.path.join(p, x)
        if os.path.exists(p):
            return os.path.abspath(p)
    return None

class CalledProcessError(Exception):
    def __init__(self, message, returncode, cmd, stdout, stderr):
        super(CalledProcessError, self).__init__(message)
        self.returncode = returncode
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr

class SchedulerNotFound(Exception):
    pass

