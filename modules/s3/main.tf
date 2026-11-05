terraform {
  required_providers {
    minio      = { source = "aminueza/minio" }
    random     = { source = "hashicorp/random" }
    kubernetes = { source = "hashicorp/kubernetes" }
  }
}
variable "name" { type = string }
variable "namespace" { type = string }
variable "config" {
  type = object({
    enabled         = bool
    targetEnvPrefix = optional(string, "S3_")
    quotaBytes      = optional(number, 2147483648)
  })
}
resource "minio_s3_bucket" "app" {
  bucket        = var.name
  acl           = "private"
  force_destroy = true
}
resource "minio_s3_bucket_quota" "app" {
  bucket = minio_s3_bucket.app.bucket
  quota  = var.config.quotaBytes
  type   = "hard"
}
resource "random_password" "s3" {
  length  = 40
  special = false
}
resource "minio_iam_user" "app" {
  name          = "ss-${var.name}"
  secret        = random_password.s3.result
  force_destroy = true
}
resource "minio_iam_policy" "app" {
  name = "ss-${var.name}"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetBucketLocation", "s3:ListBucket", "s3:ListBucketMultipartUploads"], Resource = ["arn:aws:s3:::${var.name}"] },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"], Resource = ["arn:aws:s3:::${var.name}/*"] }
    ]
  })
}
resource "minio_iam_user_policy_attachment" "app" {
  user_name   = minio_iam_user.app.name
  policy_name = minio_iam_policy.app.name
}
resource "kubernetes_secret_v1" "s3" {
  metadata {
    name      = "${var.name}-s3"
    namespace = var.namespace
  }
  data = {
    "${var.config.targetEnvPrefix}ACCESS_KEY"  = minio_iam_user.app.name
    "${var.config.targetEnvPrefix}SECRET_KEY"  = random_password.s3.result
    "${var.config.targetEnvPrefix}URL"         = "https://storage.cu3rd.ru"
    "${var.config.targetEnvPrefix}BUCKET_NAME" = minio_s3_bucket.app.bucket
  }
  depends_on = [minio_iam_user_policy_attachment.app, minio_s3_bucket_quota.app]
}
