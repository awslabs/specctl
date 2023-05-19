# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
find . -type f -name "*.tfvars" -exec sh -c 'echo "${0%/*}"' {} \; \
   | sort -u \
   | xargs -I{} sh -c "cd {}; terraform init && terraform $1 --auto-approve"
