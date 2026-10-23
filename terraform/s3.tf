resource "aws_s3_bucket" "loadtest" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_public_access_block" "loadtest" {
  bucket                  = aws_s3_bucket.loadtest.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "loadtest" {
  bucket = aws_s3_bucket.loadtest.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# k6 scripts and scenarios, uploaded from the repository. A change in any file is
# uploaded again on the next terraform apply, so S3 always matches GitHub.
resource "aws_s3_object" "scripts" {
  for_each = local.script_files

  bucket       = aws_s3_bucket.loadtest.id
  key          = "scripts/${each.value}"
  source       = "${local.repo_root}/${each.value}"
  etag         = filemd5("${local.repo_root}/${each.value}")
  content_type = endswith(each.value, ".json") ? "application/json" : "application/javascript"
}
