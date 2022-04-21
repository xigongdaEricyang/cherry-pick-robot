import * as core from '@actions/core';
// import * as github from '@actions/github'

import { inspect } from 'util';

async function run (): Promise<void> {
  const inputs = {
    fromRepo: core.getInput('from-repo'),
    repoToken: core.getInput('repo-token'),
    prLabel: core.getInput('pr-label'),
  }

  console.log(`Inputs: ${inspect(inputs)}`)
}

run();