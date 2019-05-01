workflow "Clean ECR" {
  on = "pull_request"
  resolves = "Delete branch images from ECR"
}

action "Filter merged PR" {
  uses = "actions/bin/filter@master"
  args = "merged true"
}

action "Delete branch images from ECR" {
  needs = "Filter merged PR"
  uses = "./.github/clean-ecr"
  secrets = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"]
}
