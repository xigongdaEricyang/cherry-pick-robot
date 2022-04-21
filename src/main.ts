import * as core from "@actions/core";
import * as github from "@actions/github";

import { inspect } from "util";

class Project {
  number: number;
  name: string;
  id: number;
  constructor(number: number, name: string, id: number) {
    this.number = number;
    this.name = name;
    this.id = id;
  }
}

async function run(): Promise<void> {
  try {
    const inputs = {
      fromRepo: core.getInput("from_repo"),
      repoToken: core.getInput("repo_token"),
      prLabel: core.getInput("pr_label"),
    };

    core.debug(`Inputs1: ${inspect(inputs)}`);
    console.log(`Inputs: ${inspect(inputs)}`);

    const octokit = github.getOctokit(inputs.repoToken);
    
    const { data: pullRequest } = await octokit.rest.pulls.get({
      owner: "octokit",
      repo: inputs.fromRepo,
      pull_number: 123,
      mediaType: {
        format: "diff",
      },
    });
  } catch (error: any) {
    core.debug(inspect(error));
    core.setFailed(error.message);
  }
}

run();
