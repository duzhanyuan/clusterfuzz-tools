"""Module for the Testcase class."""
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
import zipfile
import logging

from clusterfuzz import common

CLUSTERFUZZ_DIR = os.path.expanduser(os.path.join('~', '.clusterfuzz'))
CLUSTERFUZZ_TESTCASES_DIR = os.path.join(CLUSTERFUZZ_DIR, 'testcases')
CLUSTERFUZZ_TESTCASE_URL = (
    'https://%s/v2/testcase-detail/download-testcase?id=%s' %
    (common.DOMAIN_NAME, '%s'))
logger = logging.getLogger('clusterfuzz')

class Testcase(object):
  """The Testase module, to abstract away logic using the testcase JSON."""

  def get_file_extension(self, absolute_path):
    """Pulls the file extension from the path, returns '' if no extension."""
    split_filename = absolute_path.split('.')
    if len(split_filename) < 2:
      return ''
    else:
      return '.%s' % split_filename[-1]


  def get_environment_and_args(self):
    """Sets up the environment by parsing stacktrace lines."""

    new_env = {}
    args = ''
    stacktrace_lines = [l['content']  for l in self.stacktrace_lines]
    for l in stacktrace_lines:
      if '[Environment] ' in l:
        l = l.replace('[Environment] ', '')
        name, value = l.split(' = ')
        if '_OPTIONS' in name:
          value = value.replace('symbolize=0', 'symbolize=1')
          if 'symbolize=1' not in value:
            value += ':symbolize=1'
        new_env[name] = value
      elif 'Running command: ' in l:
        l = l.replace('Running command: ', '').split(' ')
        l = l[1:len(l)-1] #Strip off the binary & testcase paths
        args = " ".join(l)

    return new_env, args

  def __init__(self, testcase_json):

    self.id = testcase_json['id']
    self.stacktrace_lines = testcase_json['crash_stacktrace']['lines']
    self.environment, self.reproduction_args = self.get_environment_and_args()
    if not self.reproduction_args:
      self.reproduction_args = (
          '%s %s' %(testcase_json['testcase']['window_argument'],
                    testcase_json['testcase']['minimized_arguments']))
    self.revision = testcase_json['crash_revision']
    self.build_url = testcase_json['metadata']['build_url']
    self.job_type = testcase_json['testcase']['job_type']
    self.absolute_path = testcase_json['testcase']['absolute_path']
    self.file_extension = self.get_file_extension(self.absolute_path)
    self.reproducible = not testcase_json['testcase']['one_time_crasher_flag']
    self.gestures = testcase_json['testcase'].get('gestures')
    self.crash_type = testcase_json['crash_type']
    self.crash_state = testcase_json['crash_state']

  def testcase_dir_name(self):
    """Returns a testcases' respective directory."""
    return os.path.join(CLUSTERFUZZ_TESTCASES_DIR,
                        str(self.id) + '_testcase')

  def get_true_testcase_file(self, filename):
    """Unzips a testcase if required."""

    testcase_dir = self.testcase_dir_name()
    true_filename = os.path.join(testcase_dir,
                                 'testcase%s' % self.file_extension)

    if filename.endswith('.zip'):
      zipped_file = zipfile.ZipFile(os.path.join(testcase_dir, filename), 'r')
      zipped_file.extractall(testcase_dir)
      zipped_file.close()
      filename = self.absolute_path.split('/')[-1]

    filename = os.path.join(testcase_dir, filename)
    os.rename(filename, true_filename)
    return true_filename

  def get_testcase_path(self):
    """Downloads & returns the location of the testcase file."""

    testcase_dir = self.testcase_dir_name()
    filename = os.path.join(testcase_dir, 'testcase%s' % self.file_extension)
    if os.path.isfile(filename):
      return filename

    logger.info('Downloading testcase data...')

    if not os.path.exists(CLUSTERFUZZ_TESTCASES_DIR):
      os.makedirs(CLUSTERFUZZ_TESTCASES_DIR)
    os.makedirs(testcase_dir)

    auth_header = common.get_stored_auth_header()
    command = 'wget --content-disposition --header="Authorization: %s" "%s"' % (
        auth_header, CLUSTERFUZZ_TESTCASE_URL % self.id)
    common.execute(command, testcase_dir)
    downloaded_filename = os.listdir(testcase_dir)[0]

    filename = self.get_true_testcase_file(downloaded_filename)

    return filename