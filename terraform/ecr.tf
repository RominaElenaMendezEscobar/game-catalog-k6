resource "aws_ecr_repository" "k6" {
  name                 = "${var.name_prefix}-k6"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.force_destroy

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "report" {
  name                 = "${var.name_prefix}-report"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.force_destroy

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Every push of :latest leaves the previous image untagged: keep only the last 3 of them
resource "aws_ecr_lifecycle_policy" "cleanup" {
  for_each   = { k6 = aws_ecr_repository.k6.name, report = aws_ecr_repository.report.name }
  repository = each.value

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last 3 untagged images"
      selection = {
        tagStatus   = "untagged"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}
