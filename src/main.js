"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const tslib_1 = require("tslib");
const core = tslib_1.__importStar(require("@actions/core"));
// import * as github from '@actions/github'
const util_1 = require("util");
function run() {
    return tslib_1.__awaiter(this, void 0, void 0, function* () {
        const inputs = {
            fromRepo: core.getInput('from-repo'),
            repoToken: core.getInput('repo-token'),
            prLabel: core.getInput('pr-label'),
        };
        console.log(`Inputs: ${(0, util_1.inspect)(inputs)}`);
    });
}
run();
//# sourceMappingURL=main.js.map