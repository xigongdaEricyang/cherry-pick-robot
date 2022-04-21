"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const tslib_1 = require("tslib");
const core = tslib_1.__importStar(require("@actions/core"));
// import * as github from '@actions/github'
const util_1 = require("util");
function run() {
    return tslib_1.__awaiter(this, void 0, void 0, function* () {
        try {
            const inputs = {
                fromRepo: core.getInput('from_repo'),
                repoToken: core.getInput('repo_token'),
                prLabel: core.getInput('pr_label'),
            };
            core.debug(`Inputs1: ${(0, util_1.inspect)(inputs)}`);
        }
        catch (error) {
            core.debug((0, util_1.inspect)(error));
            core.setFailed(error.message);
        }
    });
}
run();
//# sourceMappingURL=main.js.map