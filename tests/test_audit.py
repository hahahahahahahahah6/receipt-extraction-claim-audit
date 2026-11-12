"""Offline regression suite."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from receipt_extraction_claim_audit import phrases as p
from receipt_extraction_claim_audit.audit import audit, evidence, paragraphs
from receipt_extraction_claim_audit.__main__ import main

EXPECTED_POSITIVE = ('receipt extraction', 'extract receipts', 'extracts receipts', 'extracting receipts', 'extract receipt', 'extracts receipt', 'extracting receipt', 'receipt data extraction', 'extract receipt data', 'extracts receipt data', 'extracting receipt data', 'parse receipts', 'parses receipts', 'parsing receipts', 'parse receipt', 'parses receipt', 'parsing receipt', 'receipt parsing', 'receipt parser', 'receipt field extraction', 'extract receipt fields', 'extracts receipt fields', 'extracting receipt fields', 'receipt total extraction', 'extract receipt total', 'extracts receipt total', 'receipt vendor extraction', 'extract receipt vendor', 'extracts receipt vendor', 'receipt line item extraction', 'extract receipt line items', 'extracts receipt line items', 'extracting receipt line items', 'receipt ocr extraction', 'extract data from receipts', 'extracts data from receipts', 'extracting data from receipts', 'receipt document extraction', 'extract receipt pdf', 'extracts receipt pdf', 'receipt pdf extraction', 'process receipts', 'processes receipts', 'processing receipts', 'receipt processing', 'automated receipt processing', 'receipt automation', 'extract structured receipt data', 'extracts structured receipt data', 'receipt information extraction')
EXPECTED_NEGATIVE = ('no receipt extraction', 'does not extract receipts', 'does not extract receipt', 'does not support receipt extraction', 'without receipt extraction', 'no receipt parser', 'does not parse receipts', 'does not parse receipt', 'no receipt data extraction', 'does not extract receipt data', 'no receipt field extraction', 'does not extract receipt fields', 'receipt extraction not supported', 'no receipt processing', 'does not process receipts', 'without receipt processing', 'no receipt automation', 'does not automate receipt processing', 'does not extract receipt total', 'does not extract receipt vendor', 'no receipt line item extraction', 'does not extract receipt line items', 'no receipt information extraction', 'does not extract receipt information')
EXPECTED_GENERIC = ('extract_receipt', 'extract_receipts', 'parse_receipt', 'parse_receipts', 'extract_receipt_data', 'receipt_extraction', 'receipt_extractor', 'extract_receipt_fields', 'receipt_field_extraction', 'parse_receipt_data', 'receipt_parser', 'receipt_reader', 'read_receipt', 'read_receipts', 'receipt_data_extraction', 'extract_receipt_total', 'receipt_total_extraction', 'extract_receipt_vendor', 'receipt_vendor_extraction', 'extract_receipt_line_items', 'receipt_line_item_extraction', 'parse_receipt_pdf', 'extract_receipt_pdf', 'process_receipt')

POSITIVE_ROUTES = ['import other; other.extract_receipt(x)', 'from other import extract_receipt; extract_receipt(x)', 'from other import extract_receipt as e; e(x)', 'import other as i; i.extract_receipt(x)', 'import mindee; mindee.Client(); c.parse(ReceiptV5)', 'from mindee import Client as C; C(); c.parse(TypeReceiptV5)', 'import mindee; mindee.Client(); c.parse(mindee.product.ReceiptV5)', 'import mindee; mindee.Client(); c.parse(product=documents.TypeReceiptV5)', 'import veryfi; veryfi.Client(); c.process_document(x)', 'from veryfi import Client as C; C(); c.process_document_url(x)', 'import azure.ai.formrecognizer; azure.ai.formrecognizer.DocumentAnalysisClient(); c.begin_analyze_document("prebuilt-receipt",x)', 'from azure.ai.documentintelligence import DocumentIntelligenceClient as C; C(); c.begin_analyze_document_from_url("prebuilt-receipt",x)', 'import azure.ai.formrecognizer as a; a.DocumentAnalysisClient(); c.begin_analyze_document(model_id="prebuilt-receipt")', 'import boto3; c.analyze_expense(x)', 'from boto3 import client; c.start_expense_analysis(x)', 'from other import extract_receipt as e; f = e; f()', 'from other import extract_receipt; f: object = extract_receipt; f()']
NEGATIVE_ROUTES = ['import other', 'import mindee', 'import veryfi', 'import boto3', 'import azure.ai.formrecognizer', 'import azure.ai.documentintelligence', 'extract_receipt(x)', 'import mindee; mindee.Client()', 'import veryfi; veryfi.Client()', 'import azure.ai.formrecognizer; azure.ai.formrecognizer.DocumentAnalysisClient()', 'extract_receipt()', '"receipt extraction"', '# x.extract_receipt()', 'x.extract_receipt', 'def broken(:', 'import subprocess; subprocess.run(["mindee", "x"])', 'import subprocess; subprocess.run(["veryfi", "x"])', 'import re; text = page.extract_text(); fields = {"total": re.search("total", text)}', 'import mindee; mindee.Client(); c.parse(InvoiceV4)', 'import mindee; mindee.Client(); c.parse(BankCheckV1)', 'import mindee; mindee.Client(); c.parse(PassportV1)', 'import mindee; mindee.Client(); c.parse(FinancialDocumentV1)', 'import mindee; mindee.Client(); c.parse(CustomV1)', 'import mindee; mindee.Client(); c.parse(Other)', 'import veryfi; veryfi.Client(); c.process_bank_statement_document(x)', 'import veryfi; veryfi.Client(); c.classify_document(x)', 'import veryfi; veryfi.Client(); c.process_any_document(x)', 'import azure.ai.formrecognizer; azure.ai.formrecognizer.DocumentAnalysisClient(); c.begin_analyze_document("prebuilt-invoice")', 'import azure.ai.formrecognizer; azure.ai.formrecognizer.DocumentAnalysisClient(); c.begin_analyze_document("prebuilt-layout")', 'import azure.ai.formrecognizer; azure.ai.formrecognizer.DocumentAnalysisClient(); c.begin_analyze_document("prebuilt-read")', 'import azure.ai.formrecognizer; azure.ai.formrecognizer.DocumentAnalysisClient(); c.begin_analyze_document("prebuilt-idDocument")', 'import azure.ai.formrecognizer; azure.ai.formrecognizer.DocumentAnalysisClient(); c.begin_analyze_document("other")', 'import boto3; c.analyze_document(x)', 'import boto3; c.detect_document_text(x)', 'import boto3; c.get_expense_analysis(x)', 'import pdfplumber; x.extract_text(x)', 'import fitz; x.extract_text(x)', 'import pypdf; x.extract_text(x)', 'import PyPDF2; x.extract_text(x)', 'import pdfminer; x.extract_text(x)', 'import pytesseract; x.image_to_string(x)', 'import pandas; x.read_csv(x)', 'import pandas; x.read_excel(x)', 'import camelot; x.read_pdf(x)', 'import tabula; x.read_pdf(x)', 'import tabula; x.convert_into(x)', 'import pdfplumber; x.extract_table(x)', 'import pdfplumber; x.extract_tables(x)', 'import pdfplumber; x.find_table(x)', 'import pdfplumber; x.find_tables(x)', 'import fitz; x.find_tables(x)', 'import other\ndef extract_receipt(): pass\nother.extract_receipt(x)', 'from other import extract_receipt as e\ndef e(): pass\ne(x)', 'class X:\n def extract_receipt(self): pass\nx.extract_receipt()', 'from other import extract_receipt as e\nclass extract_receipt: pass\ne()', 'from other import extract_receipt as e\ne = other\ne(x)', 'from other import extract_receipt\nwith thing() as extract_receipt: extract_receipt()', 'from other import extract_receipt\nasync def f():\n async with thing() as extract_receipt: extract_receipt()', 'from other import extract_receipt as e\ne: object = other\ne()', 'from other import extract_receipt; a=b; b=a; a(x)']

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = main(list(args))
            except SystemExit as error:
                code = error.code
        return code, out.getvalue()

    def test_phrase_oracle(self):
        tree = ast.parse(Path(p.__file__).read_text())
        literals = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
                    if isinstance(n, ast.Assign)}
        for name, expected in [('RECEIPTEXTRACTION', EXPECTED_POSITIVE),
                               ('NORECEIPTEXTRACTION', EXPECTED_NEGATIVE),
                               ('GENERIC_NAMES', EXPECTED_GENERIC)]:
            self.assertEqual(literals[name], expected)
            self.assertEqual(len(literals[name]), len(set(literals[name])))
        self.assertEqual(tuple(map(len, [EXPECTED_POSITIVE, EXPECTED_NEGATIVE, EXPECTED_GENERIC])), (50,24,24))

    def test_all_positive_phrases(self):
        for phrase in EXPECTED_POSITIVE:
            with self.subTest(phrase=phrase):
                self.write('README.md', phrase)
                self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')

    def test_all_negative_phrases(self):
        self.write('app.py', 'x.extract_receipt()')
        for phrase in EXPECTED_NEGATIVE:
            with self.subTest(phrase=phrase):
                self.write('README.md', phrase)
                result = audit(self.root)
                self.assertEqual(len(result['findings']), 1)
                self.assertEqual(result['findings'][0]['id'], 'documented-no-receipt-extraction-claim-false')

    def test_routes(self):
        sources = ['from other import other; other.extract_receipt(x)',
                   'from mindee import product; mindee.Client(); c.parse(product.ReceiptV5)',
                   'from azure.ai import formrecognizer as a; a.DocumentAnalysisClient(); c.begin_analyze_document("prebuilt-receipt")'] + POSITIVE_ROUTES + ['x.' + name + '()' for name in EXPECTED_GENERIC]
        sources += ['from other import ' + name + '; ' + name + '()' for name in EXPECTED_GENERIC]
        for source in sources:
            with self.subTest(source=source):
                self.assertTrue(evidence(source))

    def test_non_evidence(self):
        for source in NEGATIVE_ROUTES:
            with self.subTest(source=source):
                self.assertFalse(evidence(source))

    def test_pair_scope(self):
        pairs = [('import mindee; mindee.Client()', 'x.parse(ReceiptV5)'),
                 ('import veryfi; veryfi.Client()', 'x.process_document(x)'),
                 ('from azure.ai.formrecognizer import DocumentAnalysisClient; DocumentAnalysisClient()',
                  'x.begin_analyze_document("prebuilt-receipt")')]
        self.write('README.md', 'receipt extraction')
        for first, second in pairs:
            self.write('a.py', first)
            self.write('b.py', second)
            self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')

    def test_good(self):
        self.write('README.md', 'Extract receipts.')
        self.write('app.py', 'import other; other.extract_receipt("x")')
        self.assertEqual(self.cli('audit', str(self.root))[0], 0)
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_bad_json(self):
        self.write('README.md', 'Receipt extraction')
        code, output = self.cli('audit', str(self.root), '--json')
        self.assertEqual(code, 2)
        result = json.loads(output)
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual(result['findings'][0]['id'], 'documented-receipt-extraction-claim-false')
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertTrue(result['findings'][0]['message'])

    def test_test_only(self):
        self.write('README.md', 'Receipt extraction')
        for path in ['tests/app.py', 'test_app.py', 'app_test.py']:
            with self.subTest(path=path):
                file = self.write(path, 'x.extract_receipt()')
                self.assertEqual(audit(self.root)['findings'][0]['severity'], 'MEDIUM')
                self.assertEqual(self.cli('audit', str(self.root))[0], 0)
                self.assertEqual(self.cli('audit', str(self.root), '--fail-on', 'medium')[0], 2)
                file.unlink()

    def test_denial(self):
        self.write('README.md', "Doesn't extract receipts")
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.write('app.py', 'x.extract_receipt()')
        self.assertEqual(self.cli('audit', str(self.root))[0], 2)
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')

    def test_no_claim(self):
        self.write('README.md', 'A useful utility.')
        self.write('app.py', 'x.extract_receipt()')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_fences_inline_normalization(self):
        for fence in ['```', '~~~', '   ````']:
            self.write('README.md', fence + '\nextract receipts\n' + fence + '\nSafe.')
            self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.write('README.md', '`EXTRACT-RECEIPTS`')
        self.assertEqual(audit(self.root)['verdict'], 'FAIL')
        self.assertEqual(paragraphs('receipt\n extraction\n\nSafe'), ['receipt extraction','safe'])
        self.write('README.md', 'extract receiptsauce')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_scope_exclusions(self):
        self.write('README.md', 'extract receipts')
        self.write('a.py', 'import mindee; mindee.Client()')
        self.write('b.py', 'x.parse(ReceiptV5)')
        for path in ['docs/a.py','fixtures/a.py','examples/a.py']:
            self.write(path, 'x.extract_receipt()')
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')
        self.write('nested/docs/guide.md', 'does not extract receipts')
        self.write('ignored.md', 'extract receipts')
        self.assertEqual(len(audit(self.root)['findings']), 1)

    def test_symlinks(self):
        self.write('README.md', 'extract receipts')
        with tempfile.TemporaryDirectory() as other:
            path = Path(other)
            (path/'a.py').write_text('x.extract_receipt()')
            (self.root/'linked.py').symlink_to(path/'a.py')
            (self.root/'linked').symlink_to(path, target_is_directory=True)
            self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')

    def test_ignore_and_docs(self):
        self.write('docs/a.md', 'extract receipts')
        self.write('notes.md', 'extract receipts')
        self.assertEqual(self.cli('audit', str(self.root), '--ignore', 'docs', '--ignore', 'other')[0], 0)
        self.write('app.py', 'x.extract_receipt()')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.assertEqual(audit(self.root, ['app'])['verdict'], 'FAIL')

    def test_cli_errors_and_version(self):
        self.assertEqual(self.cli('--version'), (0, '0.1.0\n'))
        for args in [[], ['audit','/nonexistent-r187'], ['audit','--fail-on','HIGH'],
                     ['audit','--ignore'], ['audit','--unknown']]:
            self.assertEqual(self.cli(*args)[0], 1)
        result = subprocess.run([sys.executable, '-m', 'receipt_extraction_claim_audit', '--version'],
                                capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, '0.1.0\n'))

    def test_no_source_asymmetry(self):
        self.write('README.md', 'extract receipts')
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')
        self.write('README.md', 'does not extract receipts')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_mixed_claims_and_longest_denial(self):
        self.write('README.md', 'does not extract receipt data')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.write('README.md', 'does not extract receipt data; extract receipts')
        self.assertEqual(len(audit(self.root)['findings']), 1)
        self.write('app.py', 'x.extract_receipt()')
        self.assertEqual(audit(self.root)['findings'][0]['id'],
                         'documented-no-receipt-extraction-claim-false')

    def test_io_errors(self):
        with patch('receipt_extraction_claim_audit.audit.os.walk', side_effect=PermissionError('unreadable')):
            self.assertEqual(self.cli('audit', str(self.root))[0], 1)
        self.write('README.md', 'safe')
        with patch.object(Path, 'read_text', side_effect=PermissionError('unreadable')):
            self.assertEqual(self.cli('audit', str(self.root))[0], 1)
        (self.root/'README.md').write_bytes(bytes([255]))
        self.assertEqual(self.cli('audit', str(self.root))[0], 1)

    def test_docs_selection_and_symlink(self):
        self.write('README.md', 'safe')
        self.write('nested/docs/guide.md', 'extract receipts')
        self.assertEqual(audit(self.root)['findings'][0]['paths'], ['nested/docs/guide.md'])
        self.assertEqual(audit(self.root, ['nested'])['verdict'], 'PASS')
        (self.root/'nested/docs/guide.md').unlink()
        with tempfile.TemporaryDirectory() as other:
            path = Path(other)/'claims.md'
            path.write_text('extract receipts')
            (self.root/'nested/docs/link.md').symlink_to(path)
            self.assertEqual(audit(self.root)['verdict'], 'PASS')

if __name__ == '__main__':
    unittest.main()
