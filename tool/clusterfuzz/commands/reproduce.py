"""Module for the 'reproduce' command.

Locally reproduces a testcase given a Clusterfuzz ID."""
# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import json
import urllib
import webbrowser
import logging
import yaml

import requests

from bedrock import cmd
from clusterfuzz import common
from clusterfuzz import stackdriver_logging
from clusterfuzz import testcase
from clusterfuzz import binary_providers
from clusterfuzz import reproducers


CLUSTERFUZZ_AUTH_HEADER = 'x-clusterfuzz-authorization'
CLUSTERFUZZ_TESTCASE_INFO_URL = (
    'https://%s/v2/testcase-detail/refresh' % common.DOMAIN_NAME)
GOMA_DIR = os.path.expanduser(os.path.join('~', 'goma'))
GOOGLE_OAUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth?%s' % (
    urllib.urlencode({
        'scope': 'email profile',
        'client_id': ('981641712411-sj50drhontt4m3gjc3hordjmp'
                      'c7bn50f.apps.googleusercontent.com'),
        'response_type': 'code',
        'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob'}))
logger = logging.getLogger('clusterfuzz')


class SuppressOutput(object):
  """Suppress stdout and stderr. We need this because there's no way to suppress
    webbrowser's stdout and stderr."""

  def __enter__(self):
    self.stdout = os.dup(1)
    self.stderr = os.dup(2)
    os.close(1)
    os.close(2)
    os.open(os.devnull, os.O_RDWR)

  def __exit__(self, unused_type, unused_value, unused_traceback):
    os.dup2(self.stdout, 1)
    os.dup2(self.stderr, 2)


def get_verification_header():
  """Prompts the user for & returns a verification token."""
  print
  logger.info(('We need to authenticate you in order to get information from '
               'ClusterFuzz.'))
  print

  logger.info('Open: %s', GOOGLE_OAUTH_URL)
  with SuppressOutput():
    webbrowser.open(GOOGLE_OAUTH_URL, new=1, autoraise=True)
  print

  verification = common.ask(
      'Please login on the opened webpage and enter your verification code',
      'Please enter a code', bool)
  return 'VerificationCode %s' % verification


def send_request(url, data):
  """Get a clusterfuzz url that requires authentication.

  Attempts to authenticate and is guaranteed to either
  return a valid, authorized response or throw an exception."""

  header = common.get_stored_auth_header()
  response = None
  for _ in range(2):
    if not header or (response is not None and response.status_code == 401):
      header = get_verification_header()
    response = requests.post(
        url=url, headers={
            'Authorization': header,
            'User-Agent': 'clusterfuzz-tools'},
        allow_redirects=True, data=data)
    if response.status_code == 200:
      break

  if response.status_code != 200:
    raise common.ClusterfuzzAuthError(response.text)
  common.store_auth_header(response.headers[CLUSTERFUZZ_AUTH_HEADER])

  return response


def get_testcase_info(testcase_id):
  """Pulls testcase information from Clusterfuzz.

  Returns a dictionary with the JSON response if the
  authentication is successful.
  """

  data = json.dumps({'testcaseId': testcase_id})
  return json.loads(send_request(CLUSTERFUZZ_TESTCASE_INFO_URL, data).text)


@cmd.bind(cmd.Input('testcase_id'), priority=20)
def get_testcase(testcase_id):
  """Get testcase."""
  response = get_testcase_info(testcase_id)
  return testcase.Testcase(response)


@cmd.bind(cmd.Input('disable_goma'), cmd.Input('build'))
def should_enable_goma(disable_goma, build):
  """Return true if goma should be enabled."""
  return not disable_goma and build != 'download'


@cmd.bind(should_enable_goma, priority=20)
def get_goma_dir(goma_enabled):
  """Get goma dir."""
  if not goma_enabled:
    return False

  goma_dir = os.environ.get('GOMA_DIR', GOMA_DIR)
  if not os.path.isfile(os.path.join(goma_dir, 'goma_ctl.py')):
    raise common.GomaNotInstalledError()

  return goma_dir


@cmd.bind(should_enable_goma, get_goma_dir)
def ensure_goma(goma_enabled, goma_dir):
  """Ensures GOMA is installed and ready for use, and starts it."""
  if not goma_enabled:
    return False

  common.execute('python', 'goma_ctl.py ensure_start', goma_dir)
  return True


def parse_job_definition(job_definition, presets):
  """Reads in a job definition hash and parses it."""

  to_return = {}
  if 'preset' in job_definition:
    to_return = parse_job_definition(presets[job_definition['preset']], presets)
  for key, val in job_definition.iteritems():
    if key == 'preset':
      continue
    to_return[key] = val

  return to_return


def build_binary_definition(job_definition, presets):
  """Converts a job definition hash into a binary definition."""

  builders = {'Pdfium': binary_providers.PdfiumBuilder,
              'V8': binary_providers.V8Builder,
              'Chromium': binary_providers.ChromiumBuilder,
              'LibfuzzerMsan': binary_providers.LibfuzzerMsanBuilder,
              'MsanChromium': binary_providers.MsanChromiumBuilder,
              'CfiChromium': binary_providers.CfiChromiumBuilder,
              'UbsanVptrChromium': binary_providers.UbsanVptrChromiumBuilder}
  reproducer_map = {'Base': reproducers.BaseReproducer,
                    'LibfuzzerJob': reproducers.LibfuzzerJobReproducer,
                    'LinuxChromeJob': reproducers.LinuxChromeJobReproducer}

  result = parse_job_definition(job_definition, presets)

  return common.BinaryDefinition(
      builders[result['builder']], result['source'],
      reproducer_map[result['reproducer']], result.get('binary'),
      result.get('sanitizer'), result.get('target'))


@cmd.bind()
def get_supported_jobs():
  """Reads in supported jobs from supported_jobs.yml."""

  to_return = {
      'standalone': {},
      'chromium': {}}

  with open(common.get_resource(
      0640, 'resources', 'supported_job_types.yml')) as stream:
    job_types_yaml = yaml.load(stream)

  for build_type in ['standalone', 'chromium']:
    for job_type, job_definition in job_types_yaml[build_type].iteritems():
      try:
        to_return[build_type][job_type] = build_binary_definition(
            job_definition, job_types_yaml['presets'])
      except KeyError:
        raise common.BadJobTypeDefinitionError(
            '%s %s' % (build_type, job_type))

  return to_return


@cmd.bind(get_testcase, cmd.Input('build'), get_supported_jobs)
def get_binary_definition(testcase, build_param, supported_jobs):
  job_type = testcase.job_type

  if build_param != 'download' and job_type in supported_jobs[build_param]:
    return supported_jobs[build_param][job_type]
  else:
    for i in ['chromium', 'standalone']:
      if job_type in supported_jobs[i]:
        return supported_jobs[i][job_type]
  raise common.JobTypeNotSupportedError(job_type)


@cmd.bind(get_testcase, priority=0)
def print_warning(testcase):
  """Print warning if the testcase might not be reproducible."""
  if not testcase.reproducible:
    logger.info(
        '\nWARNING: The testcase is marked as unreproducible. Therefore, it '
        'might not be reproduced correctly here.\n')

  if testcase.gestures:
    logger.info('WARNING: The testcases use gestures and is not guaranteed to '
                'reproduce correctly.\n')


@cmd.bind(get_binary_definition, get_testcase, get_goma_dir, ensure_goma,
          cmd.Input('disable_gclient'), cmd.Input('j'), cmd.Input('build'),
          cmd.Input('current'))
def get_binary_provider(
    definition, testcase, goma_dir, _, disable_gclient, j, build, current):
  """Get binary provider."""

  if build == 'download':
    if definition.binary_name:
      binary_name = definition.binary_name
    else:
      binary_name = common.get_binary_name(testcase.stacktrace_lines)
    return binary_providers.DownloadedBinary(
        testcase.id, testcase.build_url, binary_name)
  else:
    return definition.builder(
        testcase, definition, current, goma_dir, j, disable_gclient)


@cmd.bind()
def get_blackbox_path():
  """Get blackbox path."""
  return common.check_binary('blackbox')


@cmd.bind()
def get_gclient_path():
  """Get blackbox path."""
  return common.check_binary('gclient')


@cmd.bind(get_testcase)
def get_xdotool_path(testcase):
  """Get blackbox path."""
  if not testcase.gestures:
    return False

  return common.check_binary('xdotool')


@cmd.bind(get_binary_provider)
def get_binary_path(binary_provider):
  """Get binary path."""
  return binary_provider.get_binary_path()


@cmd.bind(get_binary_provider, binary_path, get_testcase, get_binary_definition,
          print_warning, get_blackbox_path, get_gclient_path, get_xdotool_path, cmd.Input('disable_blackbox'),
          cmd.Input('target_args'), cmd.Input('iterations'))
def reproduce(
    binary_provider, testcase, definition, _, blackbox_path, gclient_path,
    xdotool_path, disable_blackbox, target_args, iterations):
  """Reproduce the crash."""
  reproducer = definition.reproducer(
      binary_provider, testcase, definition.sanitizer, disable_blackbox,
      target_args, blackbox_path, gclient_path, xdotool_path)

  try:
    reproducer.reproduce(iterations)
  finally:
    print_warning(testcase)


@stackdriver_logging.log
def execute(testcase_id, current, build, disable_goma, j,
            disable_gclient_commands, iterations, disable_blackbox,
            target_args):
  """Execute the reproduce command."""
  # logger.info('Reproducing testcase %s', testcase_id)
  # logger.debug('(testcase_id:%s, current=%s, build=%s, disable_goma=%s)',
               # testcase_id, current, build, disable_goma)
  # logger.info('Downloading testcase information...')

  cmd.execute(reproduce, [
      cmd.Input('testcase_id', testcase_id),
      cmd.Input('current', current),
      cmd.Input('build', build),
      cmd.Input('disable_goma', disable_goma),
      cmd.Input('j', j),
      cmd.Input('disable_gclient', disable_gclient_commands),
      cmd.Input('iterations', iterations),
      cmd.Input('disable_blackbox', disable_blackbox),
      cmd.Input('target_args', target_args)
  ])

  # response = get_testcase_info(testcase_id)
  # current_testcase = testcase.Testcase(response)

  # if 'gestures' in response['testcase']:
    # logger.info('Warning: testcases using gestures are not guaranteed to '
                # 'reproduce correctly.')

  # definition = get_binary_definition(current_testcase, build)

  # maybe_warn_unreproducible(current_testcase)

  # if build == 'download':
    # if definition.binary_name:
      # binary_name = definition.binary_name
    # else:
      # binary_name = common.get_binary_name(current_testcase.stacktrace_lines)
    # binary_provider = binary_providers.DownloadedBinary(
        # current_testcase.id, current_testcase.build_url, binary_name)
  # else:
    # # goma_dir = None if disable_goma else ensure_goma()
    # binary_provider = definition.builder( # pylint: disable=redefined-variable-type
        # current_testcase, definition, current, goma_dir, j,
        # disable_gclient_commands)

  # reproducer = definition.reproducer(
      # binary_provider, current_testcase, definition.sanitizer, disable_blackbox,
      # target_args)
  # reproducer.reproduce(iterations)

  # try:
    # reproducer.reproduce(iterations)
  # finally:
    # maybe_warn_unreproducible(current_testcase)
