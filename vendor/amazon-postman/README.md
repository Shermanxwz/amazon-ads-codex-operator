# Amazon Ads Postman source

`scripts/sync_amazon_postman.sh` sparsely fetches the `postman/` folder from Amazon's public `amzn/ads-advanced-tools-docs` repository at the exact commit recorded in `CERTIFIED_UPSTREAM.json`, then builds `vendor/amazon-postman/index/endpoints.json`.

The generated upstream checkout and index remain gitignored because they are reproducible build/reference artifacts. The certified commit itself is versioned so a later upstream change cannot silently alter the contract used to validate an archived release.

Amazon Ads MCP remains the primary runtime channel. The Postman snapshot is an independent API contract/reference and future deterministic fallback surface; changing the certified commit requires an explicit review and new archive gate.
