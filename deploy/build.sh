#!/bin/sh
# vercel build — the office fetches its own pages.
# every static file is pulled from this repo at a pinned commit,
# byte-exact; any missing file fails the build so a half-built site
# can never take the domain. to deploy: push the branch, update the
# pinned SHA below, then send this file + api/clerk.js to vercel
# (deploy_to_vercel, buildCommand "sh build.sh", outputDirectory
# "public", installCommand "").
set -e
R=https://raw.githubusercontent.com/maxflohr-ops/neuroforge/39718c9e12731da9597fe89b0e2341b691f2f1a4
mkdir -p public
for f in \
  index.html file.html record.html history.html bestiary.html \
  virginia.html counter.html ledger.html world.html \
  robots.txt sitemap.xml 2a0ef5f635fe22a9952ea57a7371bff3.txt \
  .well-known/atproto-did \
  assets/fonts.css assets/seal.svg assets/site.css assets/site.js \
  assets/catalog-sync.js assets/record-roll.js
do
  curl -fsS --create-dirs -o "public/$f" "$R/$f"
done
echo "fetched $(find public -type f | wc -l) files"
