#!/usr/bin/env python3

from email.mime import base
import os
import re
import sh
import time

from pathlib import Path
from github import Github
# from dingtalkchatbot.chatbot import DingtalkChatbot
from sh import git


# dingtalk_access_token = os.environ["INPUT_DINGTALK_ACCESS_TOKEN"]
# dingtalk_secret = os.environ["INPUT_DINGTALK_SECRET"]
# enable_dingtalk_notification = len(dingtalk_access_token) > 0 and len(dingtalk_secret) > 0
# dingtalk_bot = DingtalkChatbot(
#     webhook=f"https://oapi.dingtalk.com/robot/send?access_token={dingtalk_access_token}",
#     secret=dingtalk_secret,
# )

gh_url = "https://github.com"

token = os.environ['INPUT_REPO_TOKEN']
gh = Github(token)

prog = re.compile(r"(.*)\(#(\d+)\)(?:$|\n).*")
title_re = re.compile(r"(.*)(?:$|\n).*")
version_label_re = re.compile(r"^v[0-9]*\.[0-9]*")


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


def get_org_members(org_name):
    print(">>> Get org members")
    org = gh.get_organization(org_name)
    return [m.login for m in org.get_members()]


def must_create_dir(filename):
    dirname = os.path.dirname(filename)
    if len(dirname) > 0 and not os.path.exists(dirname):
        sh.mkdir('-p', dirname)


def overwrite_conflict_files(ci):
    print(">>> Overwrite PR conflict files")
    for f in ci.files:
        if f.status == "removed" and os.path.exists(f.filename):
            git.rm('-rf', f.filename)
        else:
            must_create_dir(f.filename)
            sh.curl("-fsSL", f.raw_url, "-o", f.filename)
        print(f"      {f.filename}")


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

def apply_patch(baseBranch, branch, commits):
    print(f">>> Apply patch file to {branch}")
    stopped = False
    comm_ci = commits[0] 
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
    conflict_files = []
    for ci in commits:
        try:
            git_commit = ci.commit
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
                commit_changes(ci)
                stopped = True

    try:
        git.push("-u", "origin", branch)
    except sh.ErrorReturnCode as e:
        print(">>> Fail to push branch({}) to origin, caused by {}".format(branch, e))

    return (stopped, conflict_files)


def find_latest_community_commit_in_ent_repo(ent_commit: Commit, community_commits):
    assert ent_commit.is_valid()
    for ci in community_commits:
        assert ci.is_valid()
        if ent_commit.has_same_title(ci):
            user = gh.get_user().login
            if ent_commit.login() == user:
                return ci
            else:
                print(">>> [WARN] the commit has been checkin by {} rather than {}: {}".format(
                    ent_commit.login(), user, ent_commit.title))
    return Commit()


def generate_latest_100_commits(repo):
    commits = []
    for i, ci in enumerate(repo.get_commits()):
        if i > 100:
            break
        commit = Commit(repo.get_commit(ci.sha))
        if commit.is_valid():
            commits.append(commit)
    return commits


def find_unmerged_community_commits_in_ent_repo(community_repo, ent_repo):
    ent_commits = generate_latest_100_commits(ent_repo)
    community_commits = generate_latest_100_commits(community_repo)
    for ent_commit in ent_commits:
        ci = find_latest_community_commit_in_ent_repo(
            ent_commit, community_commits)
        if ci.is_valid():
            return community_commits[:community_commits.index(ci)]
    return []


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
    return "{}\n\Cherry-pick from {}\n\n".format(body, pr_link(repo, pr))


def notify_author_by_comment(ent_repo, comm_repo, comm_ci, issue_num, comm_pr_num, org_members, conflict_files):
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

    issue = ent_repo.get_issue(issue_num)
    issue.create_comment(comment.format(ent_repo.full_name,
                                        ent_repo.name,
                                        issue_num,
                                        comm_pr_num,
                                        comm_pr_num,
                                        comm_pr_num,
                                        '\n'.join(conflict_files)))


# def create_pr(comm_repo, ent_repo, comm_ci, org_members):
#     try:
#         merged_pr = comm_repo.get_pull(comm_ci.pr_num)
#         branch = "pr-{}".format(merged_pr.number)
#         stopped, conflict_files = apply_patch(branch, comm_ci)
#         body = append_migration_in_msg(comm_repo, comm_ci, merged_pr)
#         new_pr = ent_repo.create_pull(title=comm_ci.title, body=body, head=branch, base="master")

#         print(f">>> Create PR: {pr_ref(ent_repo, new_pr)}")
#         time.sleep(2)

#         new_pr = ent_repo.get_pull(new_pr.number)
#         new_pr.add_to_labels('auto-sync')

#         if stopped:
#             notify_author_by_comment(ent_repo,
#                                      comm_repo,
#                                      comm_ci,
#                                      new_pr.number,
#                                      comm_ci.pr_num,
#                                      org_members,
#                                      conflict_files)
#             return (False, new_pr.number)

#         if not new_pr.mergeable:
#             return (False, new_pr.number)

#         commit_title = "{} (#{})".format(comm_ci.title, new_pr.number)
#         status = new_pr.merge(merge_method='squash', commit_title=commit_title)
#         if not status.merged:
#             return (False, new_pr.number)
#         return (True, new_pr.number)
#     except Exception as e:
#         print(">>> Fail to merge PR {}, cause: {}".format(comm_ci.pr_num, e))
#         return (False, -1 if new_pr is None else new_pr.number)


def get_org_name(repo):
    l = repo.split('/')
    assert len(l) == 2
    return l[0]


def get_repo_name(repo):
    l = repo.split('/')
    assert len(l) == 2
    return l[1]


def add_repo_upstream(repo):
    remote_url = 'https://github.com/{}.git'.format(repo.full_name)
    remote_name = 'origin'

    try:
        # git.init()
        git.remote('-vv')
        git.remote('rm', remote_name)
    except:
        print(">>> The remote upstream({}) not found.".format(remote_name))
    try:
        git.remote('add', remote_name, remote_url)
        git.fetch(remote_name, 'master')
    except Exception as e:
        print(">>> Fail to add remote, cause: {}".format(e))
        raise


def get_cherry_pick_pr_labels(pr):
    prLabelRegex = re.compile(r"^v[0-9]*\.[0-9]*-cherry-pick$")
    title = pr.title
    pr_labels = pr.get_labels()
    labels = [
        label.name for label in pr_labels if prLabelRegex.match(label.name)]
    return labels


def get_need_sync_prs(repo):
    prs = repo.get_pulls(state='open', sort='updated',
                         direction='desc', base='master')
    #
    return [pr for pr in prs if len(get_cherry_pick_pr_labels(pr)) > 0]


def generated_commits(repo, pr):
    commits = []
    for ci in pr.get_commits():
        commit = Commit(repo.get_commit(ci.sha))
        if commit.is_valid():
            commits.append(commit)
    return commits


def generate_pr(repo, pr):
    try:
        branch = "auto-sync-{}".format(pr.number)
        # commits = pr.get_commits()
        # print(">>> Generate commit: {}".format([commit.sha for commit in commits]))
        new_pr_title = "[auto-sync]{}".format(pr.number)
        commits = generated_commits(repo, pr)
        labels = get_cherry_pick_pr_labels(pr)
        for label in labels:
            baseBranch = 'release-{}'.format(
                version_label_re.match(label).group(0)[1:])
            body = append_cherry_pick_in_msg(repo, pr)
            stopped, conflict_files = apply_patch(baseBranch, branch, commits)
            new_pr = repo.create_pull(
                title=new_pr_title, body=body, head=branch, base=baseBranch)
            print(f">>> Create PR: {pr_link(repo, new_pr)}")
            time.sleep(2)
            new_pr = repo.get_pull(new_pr.number)
            new_pr.add_to_labels('auto-sync-robot')
    except Exception as e:
        print(">>> Fail to merge PR {}, cause: {}".format(pr.number, e))


def main(cur_repo):
    # cur_repo = gh.get_repo(repo)
    # org_members = get_org_members(get_org_name(cur_repo))

    need_sync_prs = get_need_sync_prs(cur_repo)
    for pr in need_sync_prs:
        generate_pr(cur_repo, pr)
    print(">>> {} PRs need to sync".format(len(need_sync_prs)))
    # unmerged_community_commits = find_unmerged_community_commits_in_ent_repo(comm_repo, ent_repo)
    # unmerged_community_commits.reverse()

    # add_community_upstream(comm_repo)

    # succ_pr_list = []
    # err_pr_list = []
    # for ci in unmerged_community_commits:
    #     res = create_pr(comm_repo, ent_repo, ci, org_members)
    #     md = pr_link(comm_repo, ci.pr_num)
    #     if res[1] >= 0:
    #         md += " -> " + pr_link(ent_repo, res[1])
    #     md += " " + ci.login()
    #     if res[0]:
    #         succ_pr_list.append(md)
    #         print(f">>> {pr_ref(ent_repo, res[1])} has been migrated from {pr_ref(comm_repo, ci.pr_num)}")
    #     else:
    #         err_pr_list.append(md)
    #         print(f">>> {pr_ref(comm_repo, ci.pr_num)} could not be merged into {pr_ref(ent_repo, res[1])}")
    #         break

    # succ_prs = '\n\n'.join(succ_pr_list) if succ_pr_list else "None"
    # err_prs = '\n\n'.join(err_pr_list) if err_pr_list else "None"

    # print(">>> Enable dingtalk notification: {}".format(enable_dingtalk_notification))
    # if enable_dingtalk_notification and (len(succ_pr_list) > 0 or len(err_pr_list) > 0):
    #     text = f"### Auto Merge Status\nMerge successfully:\n\n{succ_prs}\n\nFailed to merge:\n\n{err_prs}"
    #     dingtalk_bot.send_markdown(title='Auto Merge Status', text=text, is_at_all=False)

    # if len(unmerged_community_commits) == 0:
    #     print(">>> There's no any PRs to sync")


if __name__ == "__main__":
    cur_repo = os.environ["GITHUB_REPOSITORY"]
    repo = gh.get_repo(cur_repo)
    print(">>> From: {}".format(cur_repo))
    time.sleep(300000)
    add_repo_upstream(repo)
    main(repo)
