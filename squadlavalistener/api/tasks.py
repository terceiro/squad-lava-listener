import json
import logging
import requests
import urlparse

from datetime import datetime
from django.conf import settings
from squadlavalistener import celery_app
from models import Pattern
from . import  testminer
from celery.utils.log import get_task_logger
from collections import defaultdict

logger = get_task_logger(__name__)

try:
    import http.client as http_client
except ImportError:
    # Python 2
    import httplib as http_client
http_client.HTTPConnection.debuglevel = 1

# You must initialize logging, otherwise you'll not see debug output.
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

class TestJob(object):
    def __init__(self, pattern, data):
        self.pattern = pattern
        self.result = None
        self.environment = None
        self.id = data['job']
        if 'sub_id' in data.keys():
            self.id = data['sub_id']
        self.name = data['description']
        self.url = None
        self.status = data['status']
        self.definition = None
        self.initialized = False
        self.completed = False
        self.resubmitted = False
        self.data = None
        self.data_name = None
        self.testrunnerclass = "GenericLavaTestSystem"
        self.testrunnerurl = pattern.lava_server
        self.results_loaded = False
        self.metadata = None


@celery_app.task(bind=True)
def check_job_status(self, pattern, data):
    # check status of the test job in LAVA
    pattern.lava_job_status = data['status']
    # set job status and collect data
    if data['pipeline']:
        # check v2 job
        pass
    else:
        set_testjob_results.delay(pattern, data)


@celery_app.task(bind=True)
def match_pattern(self, uuid, dt, username, data):
    lava_id = data['job']
    logger.info("matching for job: %s" % lava_id)
    if 'sub_id' in data.keys():
        lava_id = data['sub_id']
    patterns = Pattern.objects.filter(is_active=True, lava_job_id=lava_id)
    for pattern in patterns:
        logger.info("pattern match %s" % pattern)
        check_job_status.delay(pattern, data)


@celery_app.task(bind=True)
#def set_testjob_results(self, testjob_id):
def set_testjob_results(self, pattern, data):
    testjob = TestJob(pattern, data)
    try:
        test_results = get_testjob_data(testjob)
        pattern.lava_job_status = testjob.status
        pattern.save()
        store_testjob_data(testjob, test_results)
    except testminer.LavaServerException as ex:
        if ex.status_code / 100 == 5:
            # HTTP 50x (internal server errors): server is too busy, in
            # maintaince, or broken; will try again later
            logger.info(ex.message)
            return
        else:
            raise


def prepare_squad_url(base_url, team, project, build, environment):
    split = urlparse.urlsplit(base_url)
    return "%s://%s/api/submit/%s/%s/%s/%s" % (split.scheme, split.netloc, team, project, build, environment)

def store_testjob_data(testjob, test_results):
    # stores test job data in SQUAD dashboard
    # results should be pushed to:
    # /team/project/build/environment path
    # the /team/project/build part should come from Pattern/build_job_name (?)
    # environment comes from testjob.environment
    #testjob.save()

    team, project, build = testjob.pattern.build_job_name.split("/")
    squad_store_url = prepare_squad_url(settings.SQUAD_URL, team, project, build, testjob.environment)

    if testjob.results_loaded:
        return

    if not test_results:
        return

    logger.debug(test_results)
    summary = defaultdict(lambda: [])

    #root_group, _ = models.BenchmarkGroup.objects.get_or_create(name='/')
    root_group = "/"

    for result in test_results:
        if 'benchmark_group' in result:
            benchmark_group = result['benchmark_group']
        else:
            benchmark_group = None
        benchmark =  name=result['benchmark_name']

        subscore_results = {}
        for item in result['subscore']:
            if item['name'] in subscore_results:
                subscore_results[item['name']].append(item['measurement'])
            else:
                subscore_results[item['name']] = [item['measurement']]

        logger.debug("subscore dict")
        logger.debug(subscore_results)
        for name, values in subscore_results.items():
            #models.ResultData.objects.create(
            #    name=name,
            #    created_at=testjob.created_at,
            #    values=values,
            #    result=testjob.result,
            #    test_job_id=testjob.id,
            #    benchmark=benchmark
            #)
            if benchmark_group:
                for v in values:
                    summary[benchmark_group].append(v)
                    summary[root_group].append(v)

    logger.debug("summary dict")
    logger.debug(summary)
#    for (gid, values) in summary.items():
#        group = models.BenchmarkGroup.objects.get(pk=gid)
#        models.BenchmarkGroupSummary.objects.create(
#            group=group,
#            environment=testjob.environment,
#            created_at=testjob.created_at,
#            result=testjob.result,
#            test_job_id=testjob.id,
#            values=values,
#        )


    testjob.results_loaded = True

    result = submit_to_squad(squad_store_url,
        team,
        None,
        subscore_results,
        testjob.metadata,
        {testjob.data_name: testjob.data})
    if result:
        testjob.pattern.is_active = False
        testjob.pattern.save()


def submit_to_squad(squad_url, team, tests=None, metrics=None, metadata=None, attachments=None):
    if team not in settings.SQUAD_TOKENS.keys():
        logger.warning("SQUAD token not found for: %s" % team)
        return False
    token = settings.SQUAD_TOKENS[team]

    if tests is None and metrics is None:
        logger.warning("No data to submit")
        return False

    headers = {
        "Auth-Token": token
    }

    payload = []
    if tests is not None:
        payload.append(("tests", json.dumps(tests)))

    if metrics is not None:
        payload.append(("metrics", json.dumps(metrics)))

    if metadata is not None:
        payload.append(("metadata", json.dumps(metadata)))

    if attachments is not None:
        for attachment_name, attachment_data in attachments.iteritems():
            if attachment_name is not None and attachment_data is not None:
                payload.append(("attachment", (attachment_name, attachment_data)))

    logger.debug(payload)

    response = requests.post(
        squad_url,
        headers=headers,
        files=payload
    )

    if response.status_code < 300:
        logger.debug("All OK")
        logger.info(response.text)
    else:
        logger.warning("Something went wrong")
        logger.warning(response.text)
        return False
    return True

def get_testjob_data(testjob):

    logger.info("Fetch benchmark results for %s" % testjob)

    netloc = urlparse.urlsplit(testjob.testrunnerurl).netloc
    if netloc not in settings.CREDENTIALS.keys():
        logger.warning("Credentials not found for %s" % netloc)
        return
    username, password = settings.CREDENTIALS[netloc]
    tester = getattr(testminer, testjob.testrunnerclass)(
        testjob.testrunnerurl, username, password
    )

    testjob.status = tester.get_test_job_status(testjob.id)
    testjob.url = tester.get_job_url(testjob.id)

    if not testjob.initialized:
        testjob.testrunnerclass = tester.get_result_class_name(testjob.id)
        testjob.initialized = True
        tester = getattr(testminer, testjob.testrunnerclass)(
            testjob.testrunnerurl, username, password
        )

    if testjob.status not in ["Complete", "Incomplete", "Canceled"]:
        logger.debug("Job({0}) status: {1}".format(testjob.id, testjob.status))
        return

    details = tester.get_test_job_details(testjob.id)
    testjob.definition = details['definition']
    testjob.metadata = details['metadata']

    # update metadata to contain mandatory fields
    #build_url: URL pointing to the origin of the build used in the test run
    #datetime: timestamp of the test run, as a ISO-8601 date representation, with seconds. This is the representation that date --iso-8601=seconds gives you.
    #job_id: identifier for the test run. Must be unique for the project.
    #job_status: string identifying the status of the project. SQUAD makes no judgement about its value.
    #job_url: URL pointing to the original test run.
    #resubmit_url: URL that can be used to resubmit the test run.
    testjob.metadata.update({"job_id": str(testjob.id)})
    testjob.metadata.update({"job_status": testjob.status})
    testjob.metadata.update({"job_url": testjob.url})
    testjob.metadata.update({"datetime": datetime.now().isoformat()})
    testjob.metadata.update({"build_url": testjob.pattern.build_job_url})

    testjob.name = details['name']
    testjob.environment = tester.get_environment_name(testjob.metadata)
    testjob.completed = True
    logger.debug("Test job({0}) completed: {1}".format(testjob.id, testjob.completed))
    if testjob.status in ["Incomplete", "Canceled"]:
        logger.debug("Job({0}) status: {1}".format(testjob.id, testjob.status))
        return

    logger.debug("Calling testminer")
    logger.debug("Tester class:{0}".format(tester.__class__.__name__))
    logger.debug("Testjob:{0}".format(testjob.id))

    test_results = tester.get_test_job_results(testjob.id)

    if not test_results and testjob.testrunnerclass != "GenericLavaTestSystem":
        testjob.status = "Results Missing"
        return

    datafile_name, datafile_content = tester.get_result_data(testjob.id)

    if datafile_name and datafile_content:
        #datafile = ContentFile(datafile_content)
        #testjob.data.save(datafile_name, datafile, save=False)
        datafile = StrinIO(datafile_content)
        testjob.data = datafile
        testjob.data_name = datafile_name

    tester.cleanup()

    # ToDo: not implemented yet. DO NOT REMOVE
    # for result in test_results['test']:
    #    name = result['testdef']
    #    if 'results' in result.keys():
    #        print "\t\tTest(%s): %s" % (name, result['result'])
    #    if 'parameters' in result.keys():
    #        print "\t\t\tParameters: %s" % (result['parameters'])
    #        print result['parameters'].__class__.__name__
    #    if 'results' in result.keys() and result['result'] == 'fail':
    #        print "\t\t\tReason: %s" % (result['reason'])
    #    version = ''
    #    if 'version' in result.keys():
    #        version = result['version']
    #    parameters = {}
    #    if 'parameters' in result.keys():
    #        parameters = result['parameters']

    return test_results

