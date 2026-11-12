"""Offline documentation and Python syntax inspection."""
import ast
import os
import re
from pathlib import Path
from . import phrases as p


def normalize(text):
    return ' '.join(text.lower().replace("n't", ' not').replace('-', ' ').split())


def paragraphs(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            lines.append('')
        elif match:
            fence = match[1]
            lines.append('')
        else:
            lines.append(line)
    return [normalize(x) for x in re.split(r'\n\s*\n', '\n'.join(lines)) if x.strip()]


def pattern(phrases):
    return re.compile(r'\b(?:' + '|'.join(re.escape(normalize(x)) for x in sorted(phrases, key=lambda x: (-len(x), x))) + r')\b')


POSITIVE = pattern(p.RECEIPTEXTRACTION)
NEGATIVE = pattern(p.NORECEIPTEXTRACTION)


def evidence(source):
    """Recognize listed calls within one syntactically valid module."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    nodes = list(ast.walk(tree))
    shadow = {n.name for n in nodes
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    aliases, bindings, gates = {}, {}, set()
    imported = set()

    def bind(target, value):
        if isinstance(target, ast.Name):
            bindings[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                bind(item, None)

    for node in nodes:
        if isinstance(node, ast.Import):
            for item in node.names:
                imported.add(item.name)
                aliases[item.asname or item.name.split('.')[0]] = (
                    item.name if item.asname else item.name.split('.')[0])
                gates.add(item.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            imported.add(module)
            gates.add(module.split('.')[0])
            for item in node.names:
                if item.name != '*':
                    aliases[item.asname or item.name] = module + '.' + item.name
                    imported.add(module + '.' + item.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                bind(target, node.value)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                bind(item.optional_vars, item.context_expr)

    def resolve(expr, seen=()):
        if isinstance(expr, ast.Name):
            if expr.id in shadow or expr.id in seen:
                return ''
            if expr.id in bindings:
                return resolve(bindings[expr.id], seen + (expr.id,))
            return aliases.get(expr.id, '')
        if isinstance(expr, ast.Attribute):
            if expr.attr in shadow:
                return ''
            base = resolve(expr.value, seen)
            return base + '.' + expr.attr if base else ''
        return ''

    def qualified(func, target):
        if resolve(func) == target:
            return True
        library, name = target.rsplit('.', 1)
        return (isinstance(func, ast.Attribute) and func.attr == name
                and isinstance(func.value, ast.Name) and func.value.id == library
                and library in gates and library not in bindings and library not in shadow)

    def usable(func):
        if isinstance(func, ast.Name):
            return func.id not in shadow
        if isinstance(func, ast.Attribute):
            base = func.value
            while isinstance(base, ast.Attribute):
                base = base.value
            return func.attr not in shadow and not (
                isinstance(base, ast.Name) and base.id in shadow)
        return False

    calls = [n for n in nodes if isinstance(n, ast.Call) and usable(n.func)]

    def constructor(library, name):
        for call in calls:
            func = call.func
            if qualified(func, library + '.' + name):
                return True
        return False

    mindee_client = 'mindee' in gates and constructor('mindee', 'Client')
    veryfi_client = 'veryfi' in gates and constructor('veryfi', 'Client')
    azure_gate = any(a.startswith(('azure.ai.formrecognizer', 'azure.ai.documentintelligence'))
                     for a in imported)
    azure_client = False
    if azure_gate:
        for call in calls:
            func = call.func
            resolved = resolve(func)
            if resolved in ('azure.ai.formrecognizer.DocumentAnalysisClient',
                            'azure.ai.documentintelligence.DocumentIntelligenceClient'):
                azure_client = True
            if isinstance(func, ast.Attribute) and func.attr in (
                    'DocumentAnalysisClient', 'DocumentIntelligenceClient'):
                base = resolve(func.value)
                if base == 'azure' or base.startswith('azure.'):
                    azure_client = True

    for call in calls:
        func = call.func
        resolved = resolve(func)
        operation = func.attr if isinstance(func, ast.Attribute) else resolved.split('.')[-1]
        if operation in shadow:
            continue
        if operation in p.GENERIC_NAMES and (
                isinstance(func, ast.Attribute) or resolved):
            return True
        if not isinstance(func, ast.Attribute):
            continue
        if mindee_client and operation == 'parse':
            args = list(call.args) + [kw.value for kw in call.keywords]
            if any((isinstance(a, ast.Name) and a.id in ('ReceiptV5', 'TypeReceiptV5'))
                   or (isinstance(a, ast.Attribute) and a.attr in ('ReceiptV5', 'TypeReceiptV5'))
                   for a in args):
                return True
        if veryfi_client and operation in ('process_document', 'process_document_url'):
            return True
        if azure_client and operation in ('begin_analyze_document', 'begin_analyze_document_from_url'):
            args = call.args[:1] + [kw.value for kw in call.keywords if kw.arg == 'model_id']
            if any(isinstance(a, ast.Constant) and a.value == 'prebuilt-receipt' for a in args):
                return True
        if 'boto3' in gates and operation in ('analyze_expense', 'start_expense_analysis'):
            return True
    return False


def audit(repo='.', ignore=()):
    root = Path(repo)
    if not root.is_dir():
        raise OSError('not a directory: ' + str(root))
    positive, negative, production, tests = [], [], [], []
    for directory, dirs, files in os.walk(root, onerror=lambda error: (_ for _ in ()).throw(error), followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink()
                         and not any((Path(directory) / d).relative_to(root).as_posix().startswith(prefix)
                                     for prefix in ignore))
        for filename in sorted(files):
            path = Path(directory) / filename
            rel = path.relative_to(root)
            if path.is_symlink() or any(rel.as_posix().startswith(prefix) for prefix in ignore):
                continue
            if rel.as_posix() == 'README.md' or (path.suffix == '.md' and 'docs' in rel.parts[:-1]):
                for para in paragraphs(path.read_text(encoding='utf-8')):
                    if NEGATIVE.search(para):
                        negative.append(rel.as_posix())
                    if POSITIVE.search(NEGATIVE.sub(' ', para)):
                        positive.append(rel.as_posix())
            if path.suffix == '.py' and not set(rel.parts[:-1]) & {'fixtures', 'docs', 'examples'}:
                if evidence(path.read_text(encoding='utf-8')):
                    is_test = 'tests' in rel.parts[:-1] or filename.startswith('test_') or filename.endswith('_test.py')
                    (tests if is_test else production).append(rel.as_posix())
    findings = []
    if positive and not production:
        findings.append(dict(id='documented-receipt-extraction-claim-false', severity='MEDIUM' if tests else 'HIGH', message='Documented capability has only test evidence.' if tests else 'Documented capability has no production evidence.', paths=sorted(set(positive))))
    if negative and production:
        findings.append(dict(id='documented-no-receipt-extraction-claim-false', severity='HIGH', message='Documented denial contradicts production evidence.', paths=sorted(set(negative))))
    return dict(verdict='FAIL' if findings else 'PASS', findings=findings, evidence=production, test_evidence=tests)
