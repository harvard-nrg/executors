Executors
=========
If you want to write scripts that will work transparently across different job 
schedulers, things can get weird pretty quickly.

Executors provides a consistent API around different job schedulers. Each 
scheduler module provides an `Executor` class with methods to `submit`, `update`,
and `cancel` jobs. With these methods at your disposal, you can build more portable 
tools quickly.

Executors also provides a special `JobArray` class for building and controlling 
collections of jobs as a single unit. There are no restrictions on the size 
or shape of jobs added to a `JobArray` and you can set behaviors such as killing 
all remaining jobs if a single job fails.

## Table of contents
1. [Installation](#installation)
2. [Supported job schedulers](#supported-job-schedulers)
3. [Usage](#usage)
   * [instantiate an executor](#instantiate-an-executor)
   * [instantiate a job](#instantiate-a-job)
   * [submit the job](#submit-the-job)
   * [update the job state](#update-the-job-state)
   * [update many job states](#update-many-job-states)
4. [Job arrays](#job-arrays)
5. [Extending Executors](#extending-executors)

## Installation
Just use pip

```bash
pip install executors
```

## Supported job schedulers
The following job schedulers are supported

* `slurm` - Simple Linux Utility for Resource Management
* `lsf` - IBM Platform LSF
* `pbsubmit` - Martinos Center Torque wrapper

## Usage
The goal is to keep this section as small as possible and get you up and running 
as quickly as possible. Here goes!

### instantiate an `Executor`
To start using Executors, you need to instantiate an `Executor` object. You can 
do this one of two ways. First, you can use `executors.probe` to automatically 
discover the scheduler present in your environment and instantiate it

```python
import executors

E = executors.probe('partition_name')
```

Or you can explicitly load an `Executor` using `executors.get`, passing in the 
type of scheduler as the first argument

```python
import executors

E = executors.get('slurm', 'partition_name')
```

Take note that you also have to pass in a `partition` argument, also known as a 
`queue` in other job schedulers.

### instantiate a `Job`
Next, you have to instantiate a `Job` object. See below for descriptions of 
supported arguments

```python
from executors.models import Job

job = Job(
    name='job',
    command=['echo', 'Hello, World!'],
    memory='100M',
    time='10',
    output='~/job-%j.stdout',
    error='~/job-%j.stderr',
    parent=parent
)
```

* `name`: Job name (required)
* `command`: Command to be executed (required)
* `memory`: Amount of memory required e.g., `1000K`, `100M`, `10G`, `1TB` (required)
* `time`: Amount of time required in seconds (required)
* `output`: Path to standard output. Any occurrence of `%j` will be replaced with Job ID.
* `error`: Path to standard error. Any occurrence of `%j` will be replaced with Job ID.
* `parent`: Parent job object a.k.a job dependency.

### submit the `Job`
Now you can submit the `Job` using your executor object `E`. Once the job has 
been submitted, the `job.pid` property will be set

```python
E.submit(job)
print('the job id is {0}'.format(job.pid))
```

### updating the `Job` state
Each `Job` object has an `active` and `returncode` property. By default, these 
are both set to `None`. These properties will be updated each time you call 
`E.update(job)`

```python
E.update(job)
print('job {0} active state is {1}'.format(job.pid, job.active))
```

> Some job schedulers will allow you to submit a job but you cannot instantly 
> query the job status, therefore Executors cannot always *guarantee* that 
> `E.update` will update the `Job` state. If you must have `E.update` wait until 
> a job is visible, add the argument `wait=True`. 

### update many `Job` states
Some job schedulers offer more efficient ways to query the state of multiple 
jobs. For that reason, if you have a `list` or `generator` of `Job` objects, 
you can pass those to the `update_many` method

```python
E.update_many(jobs)
```

> Some `Executor` objects can optimize how `update_many` is fulfilled, others 
> will resort to serially querying one job after the other. This could cause 
> a linear slow down.

# Job arrays
There are times when you want to submit several related jobs and control them 
as a group. A common need is to cancel remaining jobs if any single job has 
failed. This is what the `JobArray` class is for. Let's give it a whirl

```python
from executors.models import JobArray

jobarray = JobArray(
    executor=E,
    cancel_on_fail=True
)
jobarray.add(job_a)
jobarray.add(job_b)
jobarray.submit()
jobarray.wait()
```

## Extending Executors
It is fairly simple to extend Executors as you encounter new schedulers. First 
you must create a new module within the top-level `executors` module, for example

```bash
executors/awsbatch/__init__.py
```

Now, within this module you must create a new `Executor` class that extends 
`executors.models.AbstractExecutor`

```python
from executors.models import AbstractExecutor

class Executor(AbstractExecutor):
    ...
```

Finally you need to add your executor to the `probe` and `get` functions within 
`executors/__init__.py`.
