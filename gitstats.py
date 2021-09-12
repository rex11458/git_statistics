#!/usr/bin/env python2
# -*- coding: UTF-8 -*- 
import os
import sys
import re
import time
import json
import datetime
import ConfigParser
from pypinyin import lazy_pinyin
from git import Repo
from git.repo.fun  import is_git_dir

from utils import logger

after_date = None # "five years ago" #"2021-01-01"
until_date = None #"2021-09-10"


TIME_FORMAT = '%Y-%m-%d %H:%M'

def get_project_name(repository):
    return repository.split('/')[-1].replace(".git","")

def get_local_path(repository):
    return  os.path.join("repositories",get_project_name(repository))

def get_deploy_html_path():
    return os.path.join(os.path.abspath('.'), "html")


# from git.repo import Repo

CONFIG_FILE = 'stats_config.ini'
config = ConfigParser.ConfigParser()
config.read( CONFIG_FILE)
def get_bug_count(author, lines):
    name = author.get("pretty_name")
   
    total_bug_count = 0
    thousand_bug_count = 0
    try:
         total_bug_count = config.get('bugcount' , name) or 0
    except ConfigParser.NoOptionError as e:
        return (total_bug_count,thousand_bug_count)

    if lines != 0:
        thousand_bug_count = (float(total_bug_count) / lines) * 1000
    return int(total_bug_count) , thousand_bug_count


def read_stats_config():

    repositories = config.get('git' , 'repositories').split(',')
    after_date = config.get('period','after_date')
    if after_date is '':
        after_date = None
    until_date = config.get('period','until_date')
    if until_date is '':
        until_date = None

    return (repositories, after_date, until_date)


def getstatsummarycounts(line):
	numbers = re.findall('\d+', line)
	if   len(numbers) == 1:
		# neither insertions nor deletions: may probably only happen for "0 files changed"
		numbers.append(0);
		numbers.append(0);
	elif len(numbers) == 2 and line.find('(+)') != -1:
		numbers.append(0);    # only insertions were printed on line
	elif len(numbers) == 2 and line.find('(-)') != -1:
		numbers.insert(1, 0); # only deletions were printed on line
	return numbers    

def getallcommits(lines):
    commit_list = []
    for item in lines.splitlines():
        summary = item.split('\t')
        if len(summary) != 2:
            continue
        (record, line) = summary
        record = eval(record)
        author = record.get("author")
        commit_id = record.get("commit_id")
        commit_date = record.get("commit_date")

        if re.search('files? changed', line) != None:
            numbers = getstatsummarycounts(line)
            if len(numbers) == 3:
                (files, inserted, deleted) = map(lambda el : int(el), numbers)
                record.update({"files":files,"inserted":inserted,"deleted":deleted})
                commit_list.append(record)
    return commit_list
    

class GitRepository(object):
    """
    git仓库管理
    """

    def __init__(self, local_path, repo_url, branch='master',after_date=None,until_date=None):
        self.project_name = get_project_name(repo_url)
        self.local_path = local_path
        self.repo_url = repo_url
        self.repo = None
        self.authors = []
        self.authors_commits = []
        self.total_commits = 0
        self.after_date = after_date
        self.until_date = until_date
        self.stats_start_date = after_date
        self.stats_end_date = until_date
        self.initial(repo_url, branch)

    def initial(self, repo_url, branch):
        """
        初始化git仓库
        :param repo_url:
        :param branch:
        :return:
        """
        if not os.path.exists(self.local_path):
            os.makedirs(self.local_path)

        git_local_path = os.path.join(self.local_path, '.git')
        logger.info('')
        logger.info('*' * 30)
        logger.info(self.local_path)
        if not is_git_dir(git_local_path):
            logger.info('clone repo from origin ' + self.repo_url)
            self.repo = Repo.clone_from(repo_url, to_path=self.local_path, branch=branch)
        else:
            logger.info('create repo from local ' + self.local_path)
            self.repo = Repo(self.local_path)

    def fetch(self):
        logger.info('fetch data from origin ' + self.repo_url)
        self.repo.git.fetch(all=True)

        
        self.authors = self.get_authors()
        # logger.info(str(self.authors))
        (total_commits, author_commits,stats_start_date,stats_end_date) = self.get_all_author_commits()
        self.total_commits = total_commits
        self.authors_commits = author_commits  
        self.stats_start_date = stats_start_date
        self.stats_end_date = stats_end_date

    def get_authors(self):
        authors = []
        git_authors = self.repo.git.shortlog("-s",all=True).split("\n")
        for git_author in git_authors:
            [commit_count, author] = git_author.split('\t')

            pretty_name = ''.join(lazy_pinyin(author))

            authors.append({"git_name":author,"pretty_name":pretty_name})

        return authors
    
    def get_all_author_commits(self):
        author_commits = []
        total_commits = 0
        stats_start_date = ''
        stats_end_date = ''
        temp_min_int_date = sys.maxint
        temp_max_int_date = 0
        for author in self.authors:
            git_name = author.get("git_name")
            pretty_name = author.get("pretty_name")
            output = self.repo.git.log("--shortstat",author=git_name,pretty={"commit_id":"%h","author":"%an","commit_date":"%cd"},date='format:%Y-%m-%d %H:%M',after=self.after_date,until=self.until_date,all=True)
            commits = getallcommits(output.replace('\n\n','\t'))

            total_deleted = 0
            total_inserted = 0
            total_files = 0
            active_days = []
            for commit in commits:
                total_commits += 1
                total_deleted += commit.get("deleted") or 0
                total_inserted += commit.get("inserted") or 0
                total_files += commit.get("files") or 0

                commit_date = commit.get("commit_date") 
                if commit_date is not None:
                    date = commit_date.split(' ')
                    if len(date) == 2:
                        active_days.append(date[0])

            first_commit_date = '' #commits[-1]
            last_commit_date = '' #commits[0]


            if len(active_days) > 0:
                first_commit_date = active_days[-1]
                last_commit_date = active_days[0]
                first_date = int(first_commit_date.replace('-','')) 
                last_date = int(last_commit_date.replace('-','')) 

                if first_date < temp_min_int_date:
                    temp_min_int_date = first_date
                    stats_start_date = first_commit_date
                
                if last_date > temp_max_int_date:
                    temp_max_int_date = last_date
                    stats_end_date = last_commit_date

            
            active_days = list(set(active_days))

            (total_bug_count, thousands_bug_count) = get_bug_count(author,total_inserted)
            active_days = len(active_days)
            author_commit = {"git_name":git_name,"pretty_name":pretty_name,"commits":commits,"total_deleted":total_deleted,"total_inserted":total_inserted,"total_files":total_files,"total_bug_count":total_bug_count,"thousands_bug_count":thousands_bug_count,"first_commit_date":first_commit_date,"last_commit_date":last_commit_date,"active_days":active_days}
            author_commits.append(author_commit)

            logger.info("author:" + pretty_name + " commits:" + str(len(commits)) + " total_inserted:" + str(total_inserted) + " total_deleted:" + str(total_deleted) + " total_bug:" + str(total_bug_count) + " thousands_bug:" + str(thousands_bug_count) + " file_changes:" + str(total_files) + " first_commit_date:" + first_commit_date + " last_commit_date:"+last_commit_date + " active_days:" + str(active_days))

        return (total_commits, author_commits,stats_start_date,stats_end_date)
            
    def branches(self):
        """
        获取所有分支
        :return:
        """
        branches = self.repo.remote().refs
        return [item.remote_head for item in branches if item.remote_head not in ['HEAD', ]]

    def commits(self):
        """
        获取所有提交记录
        :return:
        """
        commit_log = self.repo.git.log('--pretty={"commit":"%h","author":"%an","summary":"%s","date":"%cd"}',
                                       max_count=50,
                                       date='format:%Y-%m-%d %H:%M')
        log_list = commit_log.split("\n")
        return [eval(item) for item in log_list]

    def tags(self):
        """
        获取所有tag
        :return:
        """
        return [tag.name for tag in self.repo.tags]

    def change_to_branch(self, branch):
        """
        切换分值
        :param branch:
        :return:
        """
        self.repo.git.checkout(branch)

    def change_to_commit(self, branch, commit):
        """
        切换commit
        :param branch:
        :param commit:
        :return:
        """
        self.change_to_branch(branch=branch)
        self.repo.git.reset('--hard', commit)

    def change_to_tag(self, tag):
        """
        切换tag
        :param tag:
        :return:
        """
        self.repo.git.checkout(tag)
    
    def get_json_data(self):
        project_name = self.project_name
        repo_url = self.repo_url
        authors = self.authors
        authors_commits = self.authors_commits     
        total_commits = self.total_commits
        stats_start_date = self.stats_start_date
        stats_end_date = self.stats_end_date
        return {
            "project_name":project_name,
            "stats_time":datetime.datetime.now().strftime(TIME_FORMAT),
            "stats_start_date":stats_start_date,
            "stats_end_date":stats_end_date,
            "repo_url":repo_url,
            "authors":authors,
            "authors_commits":authors_commits,
            "total_commits":total_commits
        }

class ReportCreator:
    def __init__(self):
        pass

    def create(self, data, path):
        self.data = data
        self.path = path

def htm_linkify(text):
    return text.lower().replace(' ','-')

def html_header(level, text):
    name = html_linkify(text)
    return '\n<h%d id="%s"><a href="#%s">%s</a></h%d>\n\n' % (level, name, name, text, level)

class HTMLReportCreator(ReportCreator):
    def create(self, data, path):
        ReportCreator.create(self,data,path)
        # self.tite = data.projectname
        f = open(path + "/data.js", 'w')

        f.write("""
        var data = %s
        """  % json.dumps(data)) 
        
        # f.write('</body>\n</html>')
        f.close()

        if sys.stdin.isatty():
            print 'You may now run:'
            print
            print '   sensible-browser \'%s\'' % os.path.join(path, 'index.html').replace("'", "'\\''")
            print





if __name__ == '__main__':
    (repositories, after_date, until_date) = read_stats_config()
    logger.info('from:' + str(after_date) + ' to:' + str(until_date))
    
    repos = []
    for repository in repositories:
        local_path = get_local_path(repository)
        repo = GitRepository(local_path,repository,after_date=after_date,until_date=until_date)
        repo.fetch()
        repos.append(repo.get_json_data())

    logger.info('Generating report...')
    report = HTMLReportCreator()
    report.create(repos,get_deploy_html_path())

    pass