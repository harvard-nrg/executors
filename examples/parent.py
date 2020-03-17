#!/usr/bin/env python

import os
import time
import logging
import executors
import argparse as ap
from executors.models import Job

logger = logging.getLogger(os.path.basename(__file__))
logging.basicConfig(level=logging.DEBUG)

def main():
    parser = ap.ArgumentParser()
    parser.add_argument('-p', '--partition', required=True)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('command', nargs=ap.REMAINDER)
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)

    # get executor
    E = executors.probe(args.partition)

    # create a job 
    logger.info('building the job object')
    parent = Job(
        command=['echo', 'parent'],
        memory='10M',
        time='10',
        name='parent',
        output='~/parent-%j.out',
        error='~/parent-%j.err'
    )

    child = Job(
        command=['echo', 'child'],
        memory='10M',
        time='10',
        name='child',
        output='~/child-%j.out',
        error='~/child-%j.err'
    )

    # submit the parent job
    logger.info('submitting the parent job')
    E.submit(parent)
    logger.info('parent job %s activity is %s', parent.pid, parent.active)
    
    # set the child parent
    child.parent = parent

    # submit the child job
    logger.info('submitting the child job')
    E.submit(child)
    logger.info('child job %s activity is %s', child.pid, child.active)
    
    # wait for parent and child jobs to complete
    while True:
        E.update(parent, wait=True)
        E.update(child, wait=True)
        if not parent.active:
            logger.info('parent job %s has finished with returncode %s', parent.pid, parent.returncode)
        if not child.active:
            logger.info('child job %s has finished with returncode %s', child.pid, child.returncode)
            break
        time.sleep(10)

if __name__ == '__main__':
    main()

