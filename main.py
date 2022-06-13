#!/usr/bin/env python3

from email.mime import base
import functools
import os
import re
import sh
import time

from pathlib import Path
from github import Github
from dingtalkchatbot.chatbot import DingtalkChatbot
from sh import git
from datetime import datetime


dingtalk_access_token = os.environ["INPUT_DINGTALK_ACCESS_TOKEN"]
dingtalk_secret = os.environ["INPUT_DINGTALK_SECRET"]
enable_dingtalk_notification = len(dingtalk_access_token) > 0 and len(dingtalk_secret) > 0
dingtalk_bot = DingtalkChatbot(
     webhook=f"https://oapi.dingtalk.com/robot/send?access_token={dingtalk_access_token}",
     secret=dingtalk_secret,
)

gh_url = "https://github.com"

token = os.environ['INPUT_REPO_TOKEN']
should_auto_merge = os.environ['INPUT_AUTO_MERGE']
label_regex = os.environ['INPUT_PR_LABEL']
gh = Github(token)

prog = re.compile(r"(.*)\(#(\d+)\)(?:$|\n).*")
title_re = re.compile(r"(.*)(?:$|\n).*")
# version_label_re = re.compile(r"^v[0-9]*\.[0-9]*(.[0-9])?")
prLabelRegex = re.compile(label_regex)
already_auto_pick_prefix = "already-auto-picked"

latest_100_commits = []


class Commit:
    def __init__(self, commit=None):
        self.commit = commit
        self.title = None
        self.pr_num = -1
        self.extract_pr_num_and_title(commit)

    def author(self):
        assert self.is_valid()
        return self.commit.commit.author

    def login(self):
        assert self.is_valid()
        return self.commit.author.login

    def is_valid(self):
        return self.commit is not None and (self.pr_num >= 0 or self.title is not None)

    def has_same_title(self, ci):
        return self.title.lower() == ci.title.lower()

    def extract_pr_num_and_title(self, commit):
        if commit is None:
            return
        msg = prog.match(commit.commit.message)
        if msg:
            self.pr_num = int(msg.group(2))
            while msg:
                self.title = msg.group(1).strip()
                msg = prog.match(self.title)
        else:
            msg = title_re.match(commit.commit.message)
            if msg:
                self.title = msg.group(1).strip()


def commit_changes(ci: Commit):
    author = ci.author()
    print(f">>> Commit changes by <{author.email}>")
    git.add(".")
    git.commit("-nam", ci.title, "--author", f"{author.name} <{author.email}>")


def conflict_file_list(lines):
    prefix = "CONFLICT (content): Merge conflict in "
    return [l[len(prefix):] for l in lines if l.startswith(prefix)]


def update_submodule(submodule_path):
    print(">>> INPUT_SUBMODULE_PATH111: {}".format(submodule_path))
    try:
        git.checkout("-q")
        git.submodule("update", "--", submodule_path)
    except sh.ErrorReturnCode as e:
        err = str(e)
        print(">>> Fail to aupdate_submodule {}, cause: {}".format(
            submodule_path, err))


def add_remote_url(repo):
    remote_url = 'https://github.com/{}.git'.format(repo.full_name)
    try:
        remote_name = repo.owner.login
        git.remote("add", remote_name, remote_url)
        git.fetch(remote_name)
    except Exception as e:
        print(">>> Fail to get remote_name, cause{}".format(str(e)))


def apply_patch(pr, baseBranch, branch, comm_ci):
    print(f">>> Apply patch file to {branch}")
    stopped = False
    cur_author = comm_ci.author()
    print(">>>> user.name: {}, user.email: {}".format(
        cur_author.name, cur_author.email))

    git.config("--local", "user.name", cur_author.name)
    git.config("--local", "user.email", cur_author.email)
    git.clean("-f")
    git.fetch("origin")
    git.checkout("-b", branch, "origin/{}".format(baseBranch))
    submodule_path = os.environ["INPUT_SUBMODULE_PATH"]
    if submodule_path:
        update_submodule(submodule_path)
    if pr.base.repo.full_name != pr.head.repo.full_name:
        add_remote_url(pr.head.repo)
    conflict_files = []
    git_commit = comm_ci.commit
    try:
        git('cherry-pick', git_commit.sha)
    except sh.ErrorReturnCode as e:
        err = str(e)
        if err.find('git commit --allow-empty') >= 0:
            git('commit', '--allow-empty',
                '--allow-empty-message', '--no-edit')
        else:
            print(">>> Fail to apply the patch to branch {}, cause: {}".format(
                branch, err))
            if err.find('more, please see e.stdout') >= 0:
                err = e.stdout.decode()
            conflict_files = conflict_file_list(err.splitlines())
            commit_changes(comm_ci)
            stopped = True

    try:
        git.push("-u", "origin", branch, "-f")
    except sh.ErrorReturnCode as e:
        print(">>> Fail to push branch({}) to origin, caused by {}".format(branch, e))

    return (stopped, conflict_files)


def generate_latest_100_commits(repo):
    # commits = []
    global latest_100_commits
    latest_100_commits = []
    for i, ci in enumerate(repo.get_commits()):
        if i > 100:
            break
        commit = Commit(repo.get_commit(ci.sha))
        # print(">>> commit: {}".format(commit.title))
        if commit.is_valid():
            latest_100_commits.append(commit)
    # print(">>>>>, commit_num, {}".format(len(latest_100_commits)))


def pr_ref(repo, pr):
    pr_num = pr if isinstance(pr, int) else pr.number
    if pr_num >= 0:
        return "{}#{}".format(repo.full_name, pr_num)
    return repo.full_name


def pr_link(repo, pr):
    pr_num = pr if isinstance(pr, int) else pr.number
    return "[{}]({}/{}/pull/{})".format(pr_ref(repo, pr_num), gh_url, repo.full_name, pr_num)


def co_authored_by(author):
    return "Co-authored-by: {} <{}>".format(author.name, author.email)


def append_migration_in_msg(repo, ci, pr):
    body = pr.body if pr.body else ""
    coauthor = co_authored_by(ci.author())
    return "{}\n\nMigrated from {}\n\n{}\n".format(body, pr_ref(repo, pr), coauthor)


def append_cherry_pick_in_msg(repo, pr):
    body = pr.body if pr.body else ""
    return "{}\nCherry-pick from {}\n\n".format(body, pr_link(repo, pr))


def notify_author_by_comment(repo, comm_ci, issue_num, comm_pr_num, org_members, conflict_files):
    comment = ""
    if comm_ci.login() in org_members:
        comment += f"@{comm_ci.login()}\n"
        print(f">>> Notify the author by comment: {comm_ci.login()}")
    else:
        print(
            f">>> The author {comm_ci.login()} is not in the orgnization, need not to notify him")

    comment += """This PR will cause conflicts when applying patch.
Please carefully compare all the changes in this PR to avoid overwriting legal codes.
If you need to make changes, please make the commits on current branch.

You can use following commands to resolve the conflicts locally:

```shell
$ git clone git@github.com:{}.git
$ cd {}
$ git remote -vv
$ git fetch origin pull/{}/head:pr-{}
$ git checkout pr-{}
# resolve the conflicts
$ git push -f origin pr-{}
```

CONFLICT FILES:
```text
{}
```
"""

    issue = repo.get_issue(issue_num)
    issue.create_comment(comment.format(repo.full_name,
                                        repo.name,
                                        issue_num,
                                        comm_pr_num,
                                        comm_pr_num,
                                        comm_pr_num,
                                        '\n'.join(conflict_files)))


def add_repo_upstream(repo):
    remote_url = 'https://github.com/{}.git'.format(repo.full_name)
    remote_name = 'origin'

    try:
        print(">>>>, remote_url, {}".format(remote_url))
        git.clone(remote_url)
        sh.cd(repo.name)
        # git.remote('-vv')
        # git.remote('rm', remote_name)
    except:
        print(">>> The remote upstream({}) not found.".format(remote_name))
    try:
        # git.remote('add', remote_name, remote_url)
        git.fetch(remote_name, 'master')
    except Exception as e:
        print(">>> Fail to add remote, cause: {}".format(e))
        raise


# def generare_sort_cmp(pr1, pr2):
    # pr_sorted_list = [
    #     commit.pr_num for commit in latest_200_commits]
    # print(">>>> sotred pr num list: {}".format(pr_sorted_list))

    # def sort_cmp(pr1, pr2):
    #     if pr1.number not in pr_sorted_list:
    #         return 1
    #     if pr2.number not in pr_sorted_list:
    #         return -1
    #     pr1_index = pr_sorted_list.index(pr1.number)
    #     pr2_index = pr_sorted_list.index(pr2.number)
    #     if pr1_index < pr2_index:
    #         return -1
    #     if pr1_index > pr2_index:
    #         return 1
    #     return 0


def getNotAutoPickedLables(labels, alreadyPickedLabels):
    newLabels = []
    for label in labels:
        full_version = getFullVersion(label)
        if "{}-{}".format(already_auto_pick_prefix, full_version) not in alreadyPickedLabels:
            newLabels.append(label)
    return newLabels


def get_cherry_pick_pr_labels(pr):
    pr_labels = pr.get_labels()
    labels = [
        label.name for label in pr_labels if prLabelRegex.match(label.name)]
    alreadyPickedLabels = [label.name for label in pr_labels if label.name.startswith(
        already_auto_pick_prefix)]
    # print("pr_num:{}, labels, {}".format(pr.number,labels))
    # print("pr_num:{}, alreadyPickedLabels, {}".format(pr.number,alreadyPickedLabels))
    newLabels = getNotAutoPickedLables(labels, alreadyPickedLabels)
    print("pr_num:{}, newLabels, {}".format(pr.number,newLabels))
    return newLabels

# old commit merged first


# def sort_pr(repo, prs):
#     sorted_prs = sorted(prs, key=functools.cmp_to_key(
#         generare_sort_cmp(repo)), reverse=True)
#     print(f">>> sorted pr list: ".format([pr.number for pr in sorted_prs]))
#     return sorted_prs

# max 100 prs


def get_need_sync_prs(repo):
    prs = []
    pr_nums = []
    for commit_ci in latest_100_commits:
        pr_num = commit_ci.pr_num
        print(">>> commit_ci.pr_num: {}".format(pr_num))
        if pr_num > 0:
          try:
            pr = repo.get_pull(pr_num)
            labels = get_cherry_pick_pr_labels(pr)
            if len(labels) > 0:
                prs.append((pr, commit_ci))
          except Exception as e:
            err = str(e)
            print(">>> Fail to get pr {} cause: {} ".format(pr_num, err))
    prs.reverse()          
    print(">>> pr total: {}".format([(pr.number, commit_ci.title) for (pr, commit_ci) in prs]))
    return prs


# def generated_commits(repo, pr):
#     commits = []
#     for ci in pr.get_commits():
#         commit = Commit(repo.get_commit(ci.sha))
#         if commit.is_valid():
#             commits.append(commit)
#     return commits

def get_org_name(repo):
    l = repo.split('/')
    assert len(l) == 2
    return l[0]

def get_org_members(org_name):
    print(">>> Get org members")
    org = gh.get_organization(org_name)
    return [m.login for m in org.get_members()]

def getFullVersion(label):
    if label.startswith('cherry-pick-'):
        return label[len('cherry-pick-'):][1:]
    if label.endswith('-cherry-pick'):
        return label[:-len('-cherry-pick')][1:]


def getBaseBranch(repo, label):
    full_version = getFullVersion(label)
    try:
        base_branch = 'release-{}'.format(full_version)
        repo.get_branch(base_branch)
        return base_branch
    except:
        base_branch = 'v{}'.format(full_version)
        try:
            repo.get_branch(base_branch)
            return base_branch
        except:
            raise Exception('base branch not found, label: {}'.format(label))


def generate_pr(repo, pr, label, commit_ci):
    try:
        org_members = get_org_members(get_org_name(repo))
        baseBranch = getBaseBranch(repo, label)
        branch = "auto-pick-{}-to-{}".format(pr.number, baseBranch)
        new_pr_title = "[auto-pick-to-{}]{}".format(baseBranch, pr.title)
        body = append_cherry_pick_in_msg(repo, pr)
        stopped, conflict_files = apply_patch(pr, baseBranch, branch, commit_ci)
        new_pr = repo.create_pull(
            title=new_pr_title, body=body, head=branch, base=baseBranch)
        print(f">>> Create PR: {pr_link(repo, new_pr)}")
        time.sleep(2)
        new_pr = repo.get_pull(new_pr.number)
        new_pr.add_to_labels('auto-pick-robot')
        
        if stopped:            
            notify_author_by_comment(repo,
                baseBranch,
                commit_ci,
                new_pr.number,
                commit_ci.pr_num,
                org_members,
                conflict_files)
            return (False, new_pr)
        
        if not new_pr.mergeable:
            return (False, new_pr)
        
        if should_auto_merge == 'true':
            commit_title = "{} (#{})".format(
                commit_ci.title, new_pr.number)
            status = new_pr.merge(merge_method='squash',
                                  commit_title=commit_title)
            if not status.merged:
                return (False, new_pr)
        pr.add_to_labels(
            '{}-{}'.format(already_auto_pick_prefix, getFullVersion(label)))
        return (True, new_pr)
    
    except Exception as e:
        print(">>> Fail to merge PR {}, cause: {}".format(pr.number, e))


def cherryPickByPrNum(repo, pr_num):
    pr = repo.get_pull(pr_num)
    for commit_ci in latest_100_commits:
        if commit_ci.pr_num == pr_num:
          return cherryPickPr(repo, [(pr, commit_ci)])

# need_sync_prs types is [pr, commit]
def cherryPickPr(cur_repo, need_sync_prs):
    succ_pr_list = []
    err_pr_list = []
    flag = 0
    
    for (pr, commit_ci) in need_sync_prs:
        print("<<< head: {}, {}".format(pr.head.repo, pr.head.ref))
        labels = get_cherry_pick_pr_labels(pr)
        print("<<< labels: {}".format(labels))
        for label in labels:
            res = generate_pr(cur_repo, pr, label, commit_ci)
            md = pr_link(cur_repo, pr)
            if res is not None:
                if res[1].number >= 0:
                    md += " -> " + pr_link(cur_repo, res[1])
                if res[0]:
                    succ_pr_list.append(md)
                    print(
                        f">>> {pr_ref(cur_repo, res[1])} has been migrated from {pr_ref(cur_repo, pr)}")
                else:
                    err_pr_list.append(md)
                    flag = 1
                    print(
                        f">>> {pr_ref(cur_repo, pr)} could not be merged into {pr_ref(cur_repo, res[1])}")
                    break
        if flag == 1:
            break
            
    succ_prs = '\n\n'.join(succ_pr_list) if succ_pr_list else "None"
    err_prs = '\n\n'.join(err_pr_list) if err_pr_list else "None"

    print(">>> Enable dingtalk notification: {}".format(enable_dingtalk_notification))
    if enable_dingtalk_notification and (len(succ_pr_list) > 0 or len(err_pr_list) > 0):
        text = f"### Auto Cherry Pick Status\nPick successfully:\n\n{succ_prs}\n\nFailed to pick:\n\n{err_prs}"
        dingtalk_bot.send_markdown(title='Auto Cherry Pick Status', text=text, is_at_all=False)
        
    print(">>> {} PRs need to sync, created {}, failed {}".format(
        len(need_sync_prs), len(succ_pr_list), len(err_pr_list)))


def cherryPickAllPrs(cur_repo):
    need_sync_prs = get_need_sync_prs(cur_repo)
    # print(f">>> Need Sync PRs: {[pr.title for pr in need_sync_prs]}")
    cherryPickPr(cur_repo, need_sync_prs)


if __name__ == "__main__":
    cur_repo = os.environ["GITHUB_REPOSITORY"]
    pr_num = os.environ["INPUT_PR_NUM"]
    repo = gh.get_repo(cur_repo)
    print(">>> From: {}".format(cur_repo))
    add_repo_upstream(repo)
    generate_latest_100_commits(repo)
    if pr_num:
        cherryPickByPrNum(repo, pr_num)
    else:
        cherryPickAllPrs(repo)
