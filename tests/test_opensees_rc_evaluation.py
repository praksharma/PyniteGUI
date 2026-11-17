"""Stored external assessment evidence; real replay is an explicit optional command."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import subprocess

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rc_external_benchmark',ROOT/'scripts/benchmark_opensees_rc.py')
benchmark=importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)


class OpenSeesRCEvaluationTests(unittest.TestCase):
    def test_recorded_engine_gates_and_sources(self):
        report=json.loads((ROOT/'docs/assets/opensees-rc-evaluation.json').read_text())
        self.assertTrue(report['passed']);self.assertTrue(all(report['checks'].values()))
        self.assertFalse(report['production_ready']);self.assertFalse(report['bundling_approved'])
        self.assertFalse(report['other_platforms_validated']);self.assertEqual(len(report['records']),8)
        self.assertEqual(report['metadata']['package'],'3.8.0.0')
        for key,limit in report['gates'].items():self.assertLess(max(r[key] for r in report['records']),limit)
        for path,digest in report['source_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)

    def test_external_rejection_invalid_json_and_timeout(self):
        for result in (subprocess.CompletedProcess([],2,'{"error":"analysis failed"}',''),subprocess.CompletedProcess([],0,'not-json','native crash'),subprocess.CompletedProcess([],0,'{"engine":"wrong"}','')):
            with patch.object(benchmark.subprocess,'run',return_value=result):
                with self.assertRaises(ValueError):benchmark.invoke('/unused/python',{'job':'steel'})
        with patch.object(benchmark.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',1)):
            with self.assertRaises(subprocess.TimeoutExpired):benchmark.invoke('/unused/python',{'job':'steel'},timeout=1)

    def test_worker_rejects_unknown_schema_before_engine_import(self):
        p=subprocess.run([sys.executable,'-I',str(ROOT/'scripts/opensees_rc_worker.py')],
            input='{"job":"execute","code":"no arbitrary code"}',text=True,capture_output=True,timeout=10)
        self.assertNotEqual(p.returncode,0);self.assertIn('error',json.loads(p.stdout))
