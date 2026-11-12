# Documentation claim auditor

An offline static auditor comparing documented promises about the checked
capability with listed call patterns in source files. It reads local files,
never executes inspected code, makes no network requests, and writes no reports
unless the caller redirects its output.

## Install and use

Requires version 3.9 or newer of the interpreter. From a source checkout:

```sh
python3 -m pip install .
receipt-extraction-claim-audit --version
receipt-extraction-claim-audit audit . --json
python3 -m receipt_extraction_claim_audit audit . --fail-on medium
receipt-extraction-claim-audit audit . --ignore vendor --ignore generated --verbose
python3 -m unittest discover
python3 -m build
```

The optional root defaults to the current directory. Each ignore argument is a
single relative path prefix and may be repeated. Threshold choices are lowercase.
Exit status is 0 when no finding reaches the threshold, 2 when one does, and 1
for usage or I/O errors. The default threshold is high, so a medium finding can
appear with status 0. JSON includes verdict, findings, evidence, and test_evidence;
each finding includes id, severity, message, and paths.

```text
documented-receipt-extraction-claim-false HIGH
 documented-receipt-extraction-claim-false MEDIUM (test evidence only)
documented-no-receipt-extraction-claim-false HIGH
```

## Scope

Only the root readme and Markdown files under a docs path component contribute
claims. Fenced blocks are excluded; inline code counts. Matching lowercases text,
expands negative contractions, replaces hyphens with spaces, and collapses
whitespace per paragraph. Exact phrases use word boundaries, longest first with
alphabetical ties; recognized denials are removed before positive matching.

Only source files with the .py suffix contribute evidence. Symlinks are skipped.
Files under fixtures, docs, and examples do not contribute; test files contribute
separately. Invalid syntax gives no evidence. Imports alone do not suffice.
A positive promise without source files is a high finding; a denial without
source files passes. One finding is emitted per claim family.

## Honest limitations

Static patterns are not semantic judgement. Broad wording can mean payment
acknowledgement or routing for approval, file-format decoding into a data model,
or optical text output intended for a human. These meanings can produce false
positives. Generic named calls can also mean a payment workflow or a wrapper
around an external binary. The listed call still counts; a thin wrapper with
only a subprocess call does not.

The two shared service routes also handle invoices, so evidence through either
satisfies the invoice family as well:

```text
Textract: analyze_expense / start_expense_analysis
Veryfi: Client + process_document / process_document_url
```

The adjacent model routes below do not count. Neither generic document analysis
nor retrieving an analysis started elsewhere starts the checked operation:

```text
Mindee: parse(InvoiceV4)
Azure: begin_analyze_document("prebuilt-invoice")
Textract: analyze_document / get_expense_analysis
```

Manual field assembly using regular expressions on recognized text is missed
without a listed call. External command line tools invoked through subprocess
are excluded, including the following:

```text
mindee CLI
veryfi CLI
```

Cloud client patterns indicate source intent, not working credentials or a
successful service call. The relevant cloud services are:

```text
Mindee, Veryfi, Azure Document Intelligence, Textract
```

Claims about invoices and printing belong to other families and do not match.
Dead code counts. Unresolved alias chains are missed. Exact wording and the
fixed denial list constrain matching; meanings and unlisted paraphrases are not
inferred. Each paired route must occur in one module. Name bindings and local
function, method, or class definitions can shadow imports; analysis is deliberately
module-wide and does not model runtime control flow or receiver types.
