import ast
import base64
import csv
import json
import os
import re
import requests
import shutil
import subprocess
import sys
import tempfile
import yaml

try:
    # try python3 first
    from xmlrpc import client as xmlrpclib
except ImportError:
    import xmlrpclib

try:
    from urllib.parse import urlsplit
except ImportError:
    from urlparse import urlsplit

from copy import deepcopy
from subprocess import Popen, PIPE, STDOUT
from celery.utils.log import get_task_logger

logger = get_task_logger("testminer")

try:
    from subprocess import DEVNULL # py3k
except ImportError:
    import os
    DEVNULL = open(os.devnull, 'wb')


def extract_metadata(definition):
    parser = MetadataParser(definition)
    return parser.metadata

def extract_name(definition):
    parser = MetadataParser(definition)
    return parser.name

def extract_device(definition):
    parser = MetadataParser(definition)
    return parser.device


class MetadataParser(object):

    def __init__(self, definition):
        self.definition = definition
        self.metadata = {}
        self.name = ""
        self.device = None
        self.__extract_metadata_recursively__(self.definition)

    def __extract_metadata_recursively__(self, data):
        if isinstance(data, dict):
            for key in data:
                if key == 'metadata':
                    for k in data[key]:
                        self.metadata[k] = data[key][k]
                elif key == 'job_name':
                    self.name = data[key]
                elif key == 'requested_device_type_id':
                    self.device = data[key]
                elif 'role' in data and 'device_type' in data and data['role'] == 'target':
                    self.device = data['device_type']
                elif not 'role' in data and 'device_type' in data:
                    self.device = data['device_type']
                else:
                    self.__extract_metadata_recursively__(data[key])
        elif isinstance(data, list):
            for item in data:
                self.__extract_metadata_recursively__(item)



def add_subscore_measurements(test_result_list, test_name, measurements):
    for i in measurements:
        test_case = {"name": test_name,
                     "measurement": i}
        test_result_list.append(test_case)


def extract_microbenchmarks(test_result_benchmarks, test_result_list):
    # Key Format: benchmarks/micro/<BENCHMARK_NAME>.<SUBSCORE>
    # Extract and unique them to form a benchmark name list
    for full_benchmark_name, measurements in test_result_benchmarks.items():
        test_result = {}
        # benchmark iteration
        benchmark_group = '/'.join(full_benchmark_name.split('/')[0:-1]) + '/'
        benchmark = full_benchmark_name.split('/')[-1].split('.')
        test_result['benchmark_name'] = benchmark[0]
        test_result['benchmark_group'] = benchmark_group
        test_result['subscore'] = []
        test_name = benchmark[1]
        add_subscore_measurements(
            test_result['subscore'],
            test_name,
            measurements)

        test_result_list.append(test_result)


def extract_compilation_statistics(test_result_statistics, test_result_list):
    for benchmark_name, benchmark_subscores in test_result_statistics.items():
        for subscore, values in benchmark_subscores.items():
            benchmark_group = "compilation statistics" + "/" + benchmark_name + "/"
            test_result = {}
            test_result['benchmark_name'] = subscore
            test_result['benchmark_group'] = benchmark_group
            test_result['subscore'] = []
            if isinstance(values, dict):
                for sub, val in values.items():
                    add_subscore_measurements(
                        test_result['subscore'],
                        sub,
                        val)
            else:
                add_subscore_measurements(
                    test_result['subscore'],
                    subscore,
                    values)
            test_result_list.append(test_result)


def parse_microbenchmark_results(test_result_dict):
    test_result_list = []
    if 'benchmarks' in test_result_dict.keys():
        test_result_benchmarks = test_result_dict['benchmarks']
        extract_microbenchmarks(test_result_benchmarks, test_result_list)

    # Extract compilation statistics
    # the format is:
    # compilation statistics/BENCHMARK_NAME/SUBSCORE/SUB_SUBSCORE
    if "compilation statistics" in test_result_dict.keys():
        test_result_statistics = test_result_dict['compilation statistics']
        extract_compilation_statistics(test_result_statistics, test_result_list)

    return test_result_list


class TestSystem(object):
    def test_results_available(self, job_id):
        return False

    def get_test_job_status(self, job_id):
        return None

    def get_test_job_results(self, job_id):
        #return dict(boot=[], test=[])
        return []

    def parse_test_results(self, data):
        return []

    def get_test_job_details(self, job_id):
        """
        returns test job metadata, for example device type
        the tests were run on
        """
        return {}

    def get_job_url(self, job_id):
        return None

    def cleanup(self):
        return None

    def get_result_class_name(self, job_id):
        return None

    def get_result_class_name_from_definition(self, definition):
        return None

    def get_result_data(self, job_id):
        return None, None

    def get_environment_name(self, metadata):
        return None

    def get_environment(self, metadata, cls):
        return self.get_environment_name(metadata)

    @staticmethod
    def reduce_test_results(test_result_list):
        return None


class LavaServerException(Exception):
    def __init__(self, url, status_code):
        self.status_code = int(status_code)
        message = "%s returned status code %d" % (url, self.status_code)
        super(Exception, self).__init__(message)


class LavaResponseException(Exception):
    pass


class GenericLavaTestSystem(TestSystem):
    XMLRPC = 'RPC2/'
    BUNDLESTREAMS = 'dashboard/streams'
    JOB = 'scheduler/job'
    def __init__(self, base_url, username=None, password=None, repo_prefix=None):
        self.url = base_url
        self.username = username # API username
        self.password = password # API token
        self.xmlrpc_url = base_url + LavaTestSystem.XMLRPC
        self.stream_url = base_url + LavaTestSystem.BUNDLESTREAMS
        self._url = base_url + LavaTestSystem.JOB
        self.result_data = None

    def test_results_available(self, job_id):
        status = self.call_xmlrpc('scheduler.job_status', job_id)
        return 'bundle_sha1' in status and len(status['bundle_sha1']) > 0

    def get_job_url(self, job_id):
        return "%s%s/%s" % (self.url, LavaTestSystem.JOB, job_id)

    def get_test_job_status(self, job_id):
        result = self.call_xmlrpc("scheduler.job_status", job_id)
        return result['job_status']

    def get_test_job_details(self, job_id):
        """
        returns test job metadata, for example device type
        the tests were run on
        """
        details = dict(testertype="lava")
        status = self.call_xmlrpc('scheduler.job_status', job_id)
        if 'bundle_sha1' in status:
            details.update({"bundle": status['bundle_sha1']})
        content = self.call_xmlrpc('scheduler.job_details', job_id)
        definition = json.loads(content['definition'])
        if content['multinode_definition']:
            definition = json.loads(content['multinode_definition'])
        details.update({"definition": str(json.dumps(definition))})
        details['metadata'] = extract_metadata(definition)
        details['metadata']['device'] = extract_device(definition)
        details['name'] = extract_name(definition)

        for action in definition['actions']:
            if action['command'].startswith("submit_results"):
                if 'stream' in action['parameters'].keys():
                    details.update({"bundlestream": action['parameters']['stream']})
        return details

    def get_result_class_name(self, job_id):
        content = self.call_xmlrpc('scheduler.job_details', job_id)
        if content['is_pipeline']:
            definition = yaml.load(content['definition'])
        else:
            definition = json.loads(content['definition'])
        return self.get_result_class_name_from_definition(definition)

    def get_result_class_name_from_definition(self, definition):
        for action in definition['actions']:
            if action['command'] == "lava_test_shell":
                if 'testdef_repos' in action['parameters'].keys():
                    for test_repo in action['parameters']['testdef_repos']:
                        if 'testdef' in test_repo.keys():
                            if test_repo['testdef'].endswith("art-microbenchmarks.yaml"):
                                return "ArtMicrobenchmarksTestResults"
                            if test_repo['testdef'].endswith("wa2host_postprocessing.yaml"):
                                return "ArtWATestResults"
                            if test_repo['testdef'].endswith("lava-android-benchmark-host.yaml"):
                                return "AndroidMultinodeBenchmarkResults"
                            if test_repo['testdef'].endswith("application-benchmark-host.yaml"):
                                return "AndroidApplicationsBenchmarkResults"
                            if test_repo['testdef'].endswith("cts-host.yaml"):
                                return "AndroidCtsTestResults"
        return "GenericLavaTestSystem"

    def call_xmlrpc(self, method_name, *method_params):
        payload = xmlrpclib.dumps((method_params), method_name)

        logger.debug(self.xmlrpc_url)
        response = requests.request('POST', self.xmlrpc_url,
                                    data = payload,
                                    headers = {'Content-Type': 'application/xml'},
                                    auth = (self.username, self.password),
                                    timeout = 100,
                                    stream = False)

        if response.status_code == 200:
            try:
                result = xmlrpclib.loads(response.content)[0][0]
                return result
            except xmlrpclib.Fault as e:
                message = "Fault code: %d, Fault string: %s\n %s" % (
                    e.faultCode, e.faultString, payload)
                raise LavaResponseException(message)
        else:
            raise LavaServerException(self.xmlrpc_url, response.status_code)

    def get_environment_name(self, metadata):
        return metadata.get('device')


class LavaV2TestSystem(GenericLavaTestSystem):
    def test_results_available(self, job_id):
        status = self.call_xmlrpc('scheduler.job_status', job_id)
        return 'bundle_sha1' in status and len(status['bundle_sha1']) > 0

    def get_test_job_details(self, job_id):
        """
        returns test job metadata, for example device type
        the tests were run on
        """
        details = dict(testertype="lava")
        status = self.call_xmlrpc('scheduler.job_status', job_id)
        if 'bundle_sha1' in status:
            details.update({"bundle": status['bundle_sha1']})
        content = self.call_xmlrpc('scheduler.job_details', job_id)
        definition = yaml.load(content['definition'])
        if content['multinode_definition']:
            definition = yaml.load(content['multinode_definition'])
        details.update({"definition": str(yaml.dump(definition))}) # keep json?
        details['metadata'] = extract_metadata(definition)
        details['metadata']['device'] = extract_device(definition)
        details['name'] = extract_name(definition)

        #for action in definition['actions']:
        #    if action['command'].startswith("submit_results"):
        #        if 'stream' in action['parameters'].keys():
        #            details.update({"bundlestream": action['parameters']['stream']})
        return details

    def get_result_class_name_from_definition(self, definition):
        return "LavaV2PassFailTestSystem"



class LavaV2PassFailTestSystem(LavaV2TestSystem):

    def get_test_job_results(self, job_id):
        ret_results = {}
        results = self.call_xmlrpc('results.get_testjob_results_yaml', job_id)
        for result in yaml.load(results):
            if result['suite'] != 'lava':
                suite = result['suite'].split("_", 1)[1]
                res_name = "%s/%s" % (suite, result['name'])
                res_value = result['result']
                ret_results.update({res_name: res_value})
        return ret_results


class LavaTestSystem(GenericLavaTestSystem):
    REPO_HOME = "/tmp/repos" # change it to cofigurable parameter
    def __init__(self, base_url, username=None, password=None, repo_prefix=None):
        self.repo_prefix = repo_prefix
        self.repo_dirs = set([])
        #self.repo_home = os.path.join(os.getcwd(), LavaTestSystem.REPO_HOME)
        self.repo_home = LavaTestSystem.REPO_HOME
        if repo_prefix:
            self.repo_home = os.path.join(
                LavaTestSystem.REPO_HOME + "/" + repo_prefix)
        super(LavaTestSystem, self).__init__(base_url, username, password)

    def cleanup(self):
        for repo_dir in self.repo_dirs:
            shutil.rmtree(repo_dir)
        if self.repo_prefix and os.path.exists(self.repo_home):
            shutil.rmtree(self.repo_home)

    def _extract_test_repos(self, testdef_repo_list):
        return_list = []
        for index, repo in enumerate(testdef_repo_list):
            if "git-repo" in repo.keys():
                return_list.append(repo)
                self._clone_test_git_repo(repo['git-repo'])
                #print "\t\t\tTest repository: %s" % repo['git-repo']
                #print "\t\t\tTest file: %s" % repo['testdef']
                #if "parameters" in repo.keys():
                #    #print "\t\t\tParameters:"
                #    for param_key, param_value in repo["parameters"].items():
                #        #print "\t\t\t\t%s: %s" % (param_key, param_value)
        return return_list

    def _escape_url(self, url):
        return url.replace(":", "_").replace("/", "_")

    def _clone_test_git_repo(self, url):
        url_escaped = self._escape_url(url)
        if not os.path.exists(self.repo_home):
            os.makedirs(self.repo_home)
        os.chdir(self.repo_home)
        if not os.path.exists(os.path.join(os.getcwd(), url_escaped)) \
            or not os.path.isdir(os.path.join(os.getcwd(), url_escaped)):
            subprocess.call(['git', 'clone', url, url_escaped], stdout=DEVNULL, stderr=subprocess.STDOUT)
        return_path = os.path.join(os.getcwd(), url_escaped)
        #os.chdir("..")
        return return_path

    def _git_checkout_and_reset(self, commit_id):
        subprocess.call(['git', 'checkout', 'master'], stdout=DEVNULL, stderr=subprocess.STDOUT)
        subprocess.call(['git', 'reset', '--hard'], stdout=DEVNULL, stderr=subprocess.STDOUT)
        subprocess.call(['git', 'pull', 'origin', 'master'], stdout=DEVNULL, stderr=subprocess.STDOUT)
        subprocess.call(['git', 'checkout', commit_id], stdout=DEVNULL, stderr=subprocess.STDOUT)

    def _find_test_file_name(self, repo_type, test_metadata, repo_url, commit_id):
        if repo_type.upper() == 'GIT':
            return self._git_find_test_file_name(test_metadata, repo_url, commit_id)

    def _git_find_test_file_name(self, test_metadata, git_repo_url, commit_id):
        os.chdir(self.repo_home)
        url_escaped = self._escape_url(git_repo_url)
        file_name_list = []
        if os.path.exists(os.path.join(os.getcwd(),url_escaped)) \
            and os.path.isdir(os.path.join(os.getcwd(),url_escaped)):
            self.repo_dirs.add(os.path.join(os.getcwd(),url_escaped))
            os.chdir(url_escaped)
            #base_path = os.getcwd()
            self._git_checkout_and_reset(commit_id)
            for root, dirs, files in os.walk('.'):
                for name in files:
                    if name.endswith("yaml"):
                        # TODO check for symlink?
                        f = open(os.path.join(os.getcwd(), root, name), 'r')
                        y = yaml.load(f.read())
                        f.close()
                        # assume tests are in Linaro format
                        #if test_medatada['name'] == y['metadata']['name'] \
                        #        and test_medatada['os'] = y['metadata']['os']:
                        if test_metadata['name'] == y['metadata']['name'] \
                            and set(test_metadata['os'].split(",")) == set(y['metadata']['os']):
                            #os.chdir("../../")
                            if len(root) > 1:
                                #return root.lstrip("./") + "/" + name
                                file_name_list.append(root.lstrip("./") + "/" + name)
                            else:
                                #return name
                                file_name_list.append(name)
        #    os.chdir("..")
        #os.chdir("..")
        #return None
        return file_name_list

    def _match_results_to_definition(
            self,
            defined_tests,
            test_location_type,
            test_location_url,
            #test_file_name,
            test_file_name_list,
            test_params,
            test_version,
            test_results):
        # update defined_tests dictionary with test results
        for result in test_results:
            if 'attachments' in result.keys():
                del result['attachments']
        for test_dict in defined_tests:
            if test_location_type.upper() == 'GIT':
                if 'git-repo' in test_dict.keys():
                    if test_dict['git-repo'] == test_location_url \
                        and test_dict['testdef'] in test_file_name_list:
                        #and test_dict['testdef'] == test_file_name:
                        # check parameters match
                        # Warning! There is no way to distinguish between
                        # identical test shells in the same job
                        # if the test is run multiple times in the same job
                        # there should be a parameter allowing to match the results
                        # to the requested test (even if the parameter is not used
                        # in the test).

                        test_file_name = test_dict['testdef']
                        if test_params:
                            f = open(
                                os.path.join(
                                    self.repo_home,
                                    self._escape_url(test_location_url),
                                    test_file_name)
                                )
                            y = yaml.load(f.read())
                            f.close()

                            default_parameters = y['params']
                            if 'parameters' in test_dict:
                                default_parameters.update(test_dict['parameters'])
                            if test_params == default_parameters:
                                # this is likely match
                                # so append test results here
                                test_dict.update({'results': test_results})
                                test_dict.update({'version': test_version})
                        else:
                            # no test_params, now what?!
                            if 'parameters' not in test_dict:
                                # looks like a match
                                test_dict.update({'results': test_results})
                                test_dict.update({'version': test_version})

    def assign_indexed_result(self, defined_tests, index, result):
        test_index = 0
        for test_key, test_dict in defined_tests.items():
            for testdef_key, testdef_dict in test_dict.items():
                if test_index == index:
                    defined_tests[test_key][testdef_key]['boot'] = deepcopy(result)
                else:
                    test_index = test_index + 1

    def match_lava_to_definition(
            self,
            defined_tests,
            lava_result_list):
        # match tests from 'lava' to corresponding shell if possible
        test_shell_found = False
        test_shell_index = 0
        lava_results = {}
        for result in lava_result_list:
            if not test_shell_found:
                if result['test_case_id'] == 'lava_test_shell':
                    test_shell_found = True
            else:
                if result['test_case_id'] == 'lava_test_shell':
                    self.assign_indexed_result(defined_tests, test_shell_index, lava_results)
                    lava_results = {}
                    test_shell_index = test_shell_index + 1
            lava_results[result['test_case_id']] = result
        self.assign_indexed_result(defined_tests, test_shell_index, lava_results)


    def get_test_job_results(self, job_id):
        """
        returns test job results
        """
        status = self.call_xmlrpc('scheduler.job_status', job_id)
        sha1 = None
        if 'bundle_sha1' in status:
            sha1 = status['bundle_sha1']
            #print "\t\tBundle SHA1: %s" % sha1
        content = self.call_xmlrpc('scheduler.job_details', job_id)
        #print "\t\tRequested device type: %s" % content['requested_device_type_id']
        definition = json.loads(content['definition'])
        if content['multinode_definition']:
            definition = json.loads(content['multinode_definition'])
        stream = None
        defined_tests = []
        all_tests = dict(boot=[], test=defined_tests)
        for action in definition['actions']:
            if action['command'] == "submit_results":
                stream = action['parameters']['stream']
            if action['command'] == "lava_test_shell":
                if 'testdef_repos' in action['parameters'].keys():
                    extracted_tests = self._extract_test_repos(action['parameters']['testdef_repos'])
                    for test in extracted_tests: defined_tests.append(test)

        if sha1:
            result_bundle = self.call_xmlrpc('dashboard.get', sha1)
            bundle = json.loads(result_bundle['content'])
            for run in iter(bundle['test_runs']):
                test_results = run['test_results']
                if run['test_id'] != 'lava':
                    meta_data = run['testdef_metadata']
                    test_location_type = meta_data['location']
                    test_location_url = meta_data['url']
                    test_version = meta_data['version']
                    test_name = meta_data['name']
                    #test_file_name = self._find_test_file_name(test_location_type, meta_data, test_location_url, test_version)
                    test_file_name_list = self._find_test_file_name(test_location_type, meta_data, test_location_url, test_version)
                    test_results = run['test_results']
                    if 'software_context' in run.keys():
                        test_source = None
                        for source in run['software_context']['sources']:
                            if source['branch_url'] == test_location_url \
                                and source['branch_revision'] == test_version:
                                test_source = source
                        test_params = {}
                        if len(test_source['default_params']) > 0:
                            # this means test_source returned empty string
                            test_params = ast.literal_eval(test_source['default_params'])
                        if len(test_source['test_params']) > 0:
                            test_params.update(ast.literal_eval(test_source['test_params']))
                        # identify matching defined test
                        self._match_results_to_definition(
                                defined_tests,
                                test_location_type,
                                test_location_url,
                                #test_file_name,
                                test_file_name_list,
                                test_params,
                                test_version,
                                test_results)
                else:
                    # process lava results
                    # these should include boot time, boot success etc.
                    # since it's almost impossible to match the tess
                    # to corresponding actions (especially in multinode)
                    # average values are added to the defined_tests
                    # as additional test with name 'boot'
                    boot_result = 'pass'
                    boot_reason = ''
                    boot_time = 0.0 #average
                    boot_samples = 0
                    userspace_boot_time = 0.0 #average
                    userspace_boot_samples = 0
                    android_userspace_boot_time = 0.0 #average
                    android_userspace_boot_samples = 0
                    test = {
                        'name': 'boot',
                        'target': run['attributes']['target'],
                        'boot_time': boot_time,
                        'boot_attempts': boot_samples}
                    for result in test_results:
                        if result['test_case_id'] == 'test_kernel_boot_time':
                            boot_time = boot_time + float(result['measurement'])
                            boot_samples = boot_samples + 1
                            if result['result'] == 'fail':
                                boot_result = 'fail'
                                boot_reason = 'kernel boot failed'
                        if result['test_case_id'] == 'test_userspace_home_screen_boot_time':
                            android_userspace_boot_time = android_userspace_boot_time + float(result['measurement'])
                            android_userspace_boot_samples = android_userspace_boot_samples + 1
                            if result['result'] == 'fail':
                                boot_result = 'fail'
                                boot_reason = 'android userspace home screen boot failed'
                        if result['test_case_id'] == 'test_userspace_boot_time':
                            userspace_boot_time = userspace_boot_time + float(result['measurement'])
                            userspace_boot_samples = userspace_boot_samples + 1
                            if result['result'] == 'fail':
                                boot_result = 'fail'
                                boot_reason = 'userspace boot failed'
                        if result['test_case_id'] == 'dummy_deploy':
                            if result['result'] == 'pass':
                                boot_samples = 1
                    if boot_time > 0:
                        boot_time = boot_time/float(boot_samples)
                        test.update({
                            'boot_time': boot_time,
                            'boot_attempts': boot_samples
                            })
                    if android_userspace_boot_time > 0:
                        android_userspace_boot_time = android_userspace_boot_time/float(android_userspace_boot_samples)
                        test.update({
                            'android_userspace_boot_time': android_userspace_boot_time,
                            'android_userspace_boot_attempts': android_userspace_boot_samples
                            })
                    if userspace_boot_time > 0:
                        userspace_boot_time = userspace_boot_time/float(userspace_boot_samples)
                        test.update({
                            'userspace_boot_time': userspace_boot_time,
                            'userspace_boot_attempts': userspace_boot_samples
                            })
                    if boot_samples == 0:
                        boot_result = 'fail'
                        boot_reason = 'No boot attempts found'
                    test['result'] = boot_result
                    test['reason'] = boot_reason
                    all_tests['boot'].append(test)
            for test in all_tests['test']:
                overall_result = 'pass'
                reason_list = []
                tests_run = 0
                tests_pass = 0
                tests_skip = 0
                tests_fail = 0
                if 'results' in test.keys():
                    tests_run = len(test['results'])
                    for result in test['results']:
                        if result['result'] == 'fail':
                            overall_result = 'fail'
                            reason_list.append(result['test_case_id'])
                            tests_fail = tests_fail + 1
                        elif result['result'] == 'skip':
                            tests_skip = tests_skip + 1
                        elif result['result'] == 'pass':
                            tests_pass = tests_pass + 1
                else:
                    overall_result = 'fail'
                    reason_list.append('Test Results Missing!')
                test['result'] = overall_result
                test['reason'] = ",".join(reason_list)
                test['total_count'] = tests_run
                test['pass_count'] = tests_pass
                test['skip_count'] = tests_skip
                test['fail_count'] = tests_fail

        return all_tests

    @staticmethod
    def reduce_test_results(test_result_list):
        if len(test_result_list) < 1:
            return None
        test_result_set = set(test_result_list)
        if len(test_result_set) == 1:
            return test_result_set.pop()
        else:
            if 'red' in test_result_set:
                return 'red'
            if 'yellow' in test_result_set:
                return 'yellow'
            if 'green' in test_result_set: # in case there is green and N/A
                return 'green'
        return None

class ArtMicrobenchmarksTestResults(LavaTestSystem):
    def get_test_job_results(self, test_job_id):
        (json_filename, json_text) = self.get_result_data(test_job_id)
        if json_text:
            return self.parse_test_results(json_text)
        else:
            return []

    def parse_test_results(self, json_text):
        test_result_dict = json.loads(json_text)
        return parse_microbenchmark_results(test_result_dict)

    def get_result_data(self, test_job_id):
        status = self.call_xmlrpc('scheduler.job_status', test_job_id)

        if not ('bundle_sha1' in status and status['bundle_sha1']):
            return (None, None)

        sha1 = status['bundle_sha1']
        result_bundle = self.call_xmlrpc('dashboard.get', sha1)
        bundle = json.loads(result_bundle['content'])

        host = [t for t in bundle['test_runs'] if t['test_id'] == 'art-microbenchmarks']
        if host:
            host = host[0]
        else:
            return (None, None)
        json_attachments = [(a['pathname'], a['content']) for a in host['attachments'] if a['pathname'].endswith('json')]

        if not json_attachments:
            return (None, None)
        return (json_attachments[0][0], base64.b64decode(json_attachments[0][1]))

    def get_environment_name(self, metadata):
        wanted = ('device', 'mode', 'core', 'compiler-mode')
        data = { 'compiler-mode': 'aot' } # defaults
        data.update(metadata)
        environment = [ str(data[key]) for key in wanted if key in data ]
        if len(environment) == len(wanted):
            return '-'.join(environment)
        else:
            return None


class ArtWATestResults(LavaTestSystem):
    def get_test_job_results(self, test_job_id):
        (db_filename, db_content) = self.get_result_data(test_job_id)
        if db_content:
            return self.parse_test_results(db_content)
        else:
            return []

    def parse_test_results(self, db_content):
        # select iteration, workload, metric, value from results;
        test_result_dict = {}
        if db_content:
            import sqlite3

            db_file = tempfile.NamedTemporaryFile(delete=False)
            db_file.write(db_content)
            db_file.close()
            conn = sqlite3.connect(db_file.name)
            cursor = conn.cursor()
            for row in cursor.execute("select iteration, workload, metric, value from results"):
                if row[1] in test_result_dict.keys():
                    test_result = test_result_dict[row[1]]
                    test_result['subscore'].append({
                            'name': row[2],
                            'measurement': float(row[3])
                        })
                else:
                    test_result = {}
                    # benchmark iteration
                    test_result['benchmark_name'] = row[1]
                    test_result['subscore'] = [{
                            'name': row[2],
                            'measurement': float(row[3])
                        }]
                    test_result_dict[row[1]] = test_result
            os.unlink(db_file.name)
        return [value for key, value in test_result_dict.items()]

    def get_result_data(self, test_job_id):
        status = self.call_xmlrpc('scheduler.job_status', test_job_id)

        if not ('bundle_sha1' in status and status['bundle_sha1']):
            return (None, None)

        sha1 = status['bundle_sha1']
        result_bundle = self.call_xmlrpc('dashboard.get', sha1)
        bundle = json.loads(result_bundle['content'])

        host = [t for t in bundle['test_runs'] if t['test_id'] == 'wa2-host-postprocessing']
        if host:
            host = iter(host).next()
        else:
            return (None, None)
        db_attachments = [(a['pathname'], a['content']) for a in host['attachments'] if a['pathname'].endswith('db')]

        if not db_attachments:
            return (None, None)
        return (db_attachments[0][0], base64.b64decode(db_attachments[0][1]))


class AndroidMultinodeBenchmarkResults(LavaTestSystem):
    def __init__(self, *args):
        self.host_test_id = "lava-android-benchmark-host"
        super(AndroidMultinodeBenchmarkResults, self).__init__(*args)

    def get_test_job_results(self, test_job_id):
        if self.host_test_id == None:
            return []
        logger.debug("Multinode measurement parsing from: {0}".format(self.host_test_id))

        status = self.call_xmlrpc('scheduler.job_status', test_job_id)

        if not ('bundle_sha1' in status and status['bundle_sha1']):
            return []

        sha1 = status['bundle_sha1']
        result_bundle = self.call_xmlrpc('dashboard.get', sha1)
        bundle = json.loads(result_bundle['content'])

        target = [t for t in bundle['test_runs'] if t['test_id'] in ['multinode-target', 'lava-android-benchmark-target', 'target-stop']]
        if target:
            target = target[0]
        else:
            return []
        host = [t for t in bundle['test_runs'] if t['test_id'] == self.host_test_id]
        if host:
            host = host[0]
        else:
            return []

        if 'test_results' not in host.keys():
            return []
        test_result_dict = {}
        for test in host['test_results']:
            if 'measurement' in test.keys():
                if "_" in test['test_case_id']:
                    benchmark, test_case_name = test['test_case_id'].split("_", 1)
                elif "-" in test['test_case_id']:
                    #workaround for benchmarks that don't preserve naming convention
                    benchmark, test_case_name = test['test_case_id'].split("-", 1)
                else:
                    benchmark = test['test_case_id']
                    test_case_name = "Score"
                if benchmark in test_result_dict.keys():
                    test_result = test_result_dict[benchmark]
                    test_result['subscore'].append(
                            {"name": test_case_name,
                             "measurement": float(test['measurement'])
                            })
                else:
                    test_result = {}
                    test_result['board'] = target['attributes']['target']
                    test_result['board_config'] = target['attributes']['target']
                    # benchmark iteration
                    test_result['benchmark_name'] = benchmark
                    test_result['subscore'] = [
                            {"name": test_case_name,
                             "measurement": float(test['measurement'])
                            }]
                    test_result_dict[benchmark] = test_result
        return [value for key, value in test_result_dict.items()]


class AndroidApplicationsBenchmarkResults(AndroidMultinodeBenchmarkResults):
    def __init__(self, *args):
        super(AndroidApplicationsBenchmarkResults, self).__init__(*args)
        self.host_test_id = "application-benchmark-host"


class AndroidCtsTestResults(AndroidMultinodeBenchmarkResults):
    def __init__(self, *args):
        super(AndroidCtsTestResults, self).__init__(*args)
        self.host_test_id = "cts-host"
