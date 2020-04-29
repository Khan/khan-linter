#!/usr/bin/env bash
set -e

# This is a script to test the pre-push lint hook in githook.py. It creates a
# test repository, installs the lint git hook, then runs a series of tests to
# confirm that the right files are linted on push, and that lint failure aborts
# the push. If the test passed, it will output "Test passed!".
#
# Unfortuantely, this script doesn't *automatically* assert that the correct
# files are linted. To verify this, add a temporary line of code to githook.py
# that prints the set of linted files, then manually check the output against
# the "Confirm:" lines outputted by this script.
#
# TODO(mdr): It'd be nice if this script *automatically* asserted that the
#     right files are linted. I'm not sure it's worth building the necessary
#     infra right now, though, since this probably won't be a high-traffic area
#     of the KA codebase. But, if that changes, let's upgrade this script!

remote_repo_path=$(mktemp -d -t lint-hook-test-remote.XXXXXX)
local_repo_path=$(mktemp -d -t lint-hook-test-local.XXXXXX)
function finish {
  rm -rf $remote_repo_path
  rm -rf $local_repo_path
}
trap finish EXIT

# Create a local git repository to serve as the "remote" repository.
echo '>> Initialize "remote" repo.'
git init --bare $remote_repo_path
echo ''

# Create a local git repository to serve as the "local" repository.
# Initialize it, set up the remote, and add the khan-linter git hook.
echo '>> Initialize "local" repo.'
cd $local_repo_path
git init
git remote add origin $remote_repo_path
git commit --allow-empty -m 'initial commit'
git push -u origin master
mkdir -p .git/hooks
echo '~/khan/devtools/khan-linter/githook.py --hook=pre-push "$@"' > .git/hooks/pre-push
chmod +x .git/hooks/pre-push
echo ''

echo ''
echo '>> Push. (Changes: <none>.)'
echo '>> Confirm: No files are linted, push succeeds.'
git push
echo ''

echo '>> Commit. (Changes: Add A and B.)'
touch A.js B.js
git add A.js B.js
git commit -m 'Add A and B.'
git tag add-A-and-B
echo ''

echo '>> Push. (Changes: Add A and B.)'
echo '>> Confirm: A and B are linted, push succeeds.'
git push
echo ''

echo '>> Commit. (Changes: Modify A to fail linting.)'
echo 'foo' > A.js
git add A.js
git commit -m 'Modify A to fail linting.'
echo ''

echo '>> Push. (Changes: Modify A to fail linting.)'
echo '>> Confirm: A is linted, push fails.'
! git push
echo ''

echo '>> Push with no-lint envvar set.'
echo '>> Confirm: A is not linted, push succeeds.'
env GIT_LINT=no git push
echo ''

echo '>> Revert changes to A.'
git reset --hard add-A-and-B
git push -f
echo ''

echo '>> Commit. (Changes: Add C, which fails linting.)'
echo 'foo' > C.js
git add C.js
git commit -m 'Add C, which fails linting.'
echo ''

echo '>> Push. (Changes: Add C, which fails linting.)'
echo '>> Confirm: C is linted, push fails.'
! git push
echo ''

echo '>> Revert creation of C.'
git reset --hard add-A-and-B
echo ''

echo '>> Create feature branch.'
git checkout -b feature-branch
echo ''

echo '>> Commit. (Changes: Add D on feature branch.)'
touch D.js
git add D.js
git commit -m 'Add D on feature branch.'
echo ''

echo '>> Checkout master.'
git checkout master
echo ''

echo '>> Commit. (Changes: Add E.)'
touch E.js
git add E.js
git commit -m 'Add E.'
echo ''

echo '>> Push. (Changes: Add E.)'
echo '>> Confirm: E is linted, push succeeds.'
git push
echo ''

echo '>> Checkout feature branch.'
git checkout feature-branch
echo ''

echo '>> Merge master.'
git merge master --no-edit
echo ''

echo '>> Push feature branch. (Changes: Add E on feature branch, merge D from master.)'
echo '>> Confirm: D is linted, E is NOT linted (not necessary, since master was pushed earlier), push succeeds.'
git push origin feature-branch
echo ''

echo '>> Commit. (Changes: Add F to feature branch.)'
touch F.js
git add F.js
git commit -m 'Add F to feature branch.'
echo ''

echo '>> Checkout master.'
git checkout master
echo ''

echo '>> Commit. (Changes: Add G.)'
touch G.js
git add G.js
git commit -m 'Add G.'
echo ''

echo '>> (Unlike last time, do NOT push to master.)'
echo ''

echo '>> Checkout feature branch.'
git checkout feature-branch
echo ''

echo '>> Merge master.'
git merge master --no-edit
echo ''

echo '>> Push. (Changes: Add F to feature branch, merge G from master.)'
echo '>> Confirm: F and G are linted, push succeeds.'
git push origin feature-branch
echo ''

echo '>> Delete the branch.'
echo '>> Confirm: no lint runs, push succeeds.'
git push origin --delete feature-branch

echo 'Test passed!'
