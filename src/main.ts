import * as core from '@actions/core';
// import * as github from '@actions/github'

import { inspect } from 'util';

async function run (): Promise<void> {
  try {
    const inputs = {
      fromRepo: core.getInput('from_repo'),
      repoToken: core.getInput('repo_token'),
      prLabel: core.getInput('pr_label'),
    }
  
    core.debug(`Inputs: ${inspect(inputs)}`)
  } catch (error: any) {
    core.debug(inspect(error))
    core.setFailed(error.message)
  }

}

run();