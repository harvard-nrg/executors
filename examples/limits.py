#!/usr/bin/env python

import executors
import logging
import argparse as ap
from executors.models import JobArray,Job

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

def main():
    parser = ap.ArgumentParser()
    parser.add_argument('-p', '--partition')
    args = parser.parse_args()
    
    E = executors.probe(args.partition)
    arr = JobArray(E, cancel_on_fail=True)    

    chaos = Job(
        name='chaos',
        command=['asdf'],
        memory='10M',
        time='00:00:12',
        output='/dev/null',
        error='/dev/null'
    )

    for i in range(1, 11):
        j = Job(
            name='sleep {0}'.format(i),
            command=['sleep', '10'],
            memory='10M',
            time='00:00:12',
            output='/dev/null',
            error='/dev/null'
        )
        if i == 4:
            arr.add(chaos)
        arr.add(j)

    arr.submit(limit=3)
    logger.info('%s jobs failed', len(arr.failed))
    logger.info('%s jobs completed', len(arr.complete))

if __name__ == '__main__':
    main()
