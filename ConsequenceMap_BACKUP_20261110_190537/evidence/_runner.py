
import json, sys, unittest
ROOT = r"C:\Users\Utente\Desktop\ConsequenceMap"
sys.path.insert(0, ROOT)
loader = unittest.TestLoader()
suite = loader.discover(start_dir=ROOT, pattern="test_*.py", top_level_dir=ROOT)
def walk(s):
    for item in s:
        if isinstance(item, unittest.TestSuite):
            yield from walk(item)
        elif item is not None:
            yield item.id()
ids = list(walk(suite))
result = unittest.TestResult()
suite.run(result)
err = {t.id() for t, _ in result.errors}
fail = {t.id() for t, _ in result.failures}
out = {tid: ("FAIL" if tid in fail else ("ERROR" if tid in err else "ok")) for tid in ids}
print("###JSON###")
print(json.dumps({"tests": out, "total": result.testsRun,
                  "failures": len(result.failures), "errors": len(result.errors)}, indent=1))
