import sys,unittest,tempfile,json,zipfile,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from updater import check

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root=Path(self.temp.name).resolve()
        self.app=self.root/'app'; self.app.mkdir()
        self.feed=self.root/'feed'; self.feed.mkdir()
        for name,data in {'app.py':'old=1','targeting.py':'x=1','requirements.txt':'','README.md':'old'}.items():
            (self.app/name).write_text(data)
        (self.app/'version.txt').write_text('1.0.0')
        (self.app/'update-source.json').write_text(json.dumps({'manifest':str(self.feed/'manifest.json')}))
        (self.app/'yolo11n-pose.pt').write_bytes(b'keep model')
    def tearDown(self): self.temp.cleanup()
    def publish(self,files=None,release='1.1.0'):
        files=files or {'app.py':'new=2','targeting.py':'x=2','requirements.txt':'','README.md':'new'}
        package=self.feed/f'hazmob-{release}.zip'
        with zipfile.ZipFile(package,'w') as z:
            for name,data in files.items(): z.writestr(name,data)
        (self.feed/'manifest.json').write_text(json.dumps({'version':release,'package':package.name,'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}))
        return package
    def test_valid_atomic_update_and_repeat(self):
        self.publish(); result=check(self.app)
        self.assertEqual(result['version'],'1.1.0')
        self.assertEqual((Path(result['path'])/'app.py').read_text(),'new=2')
        self.assertEqual(check(self.app)['status'],'Up to date.')
        self.assertEqual((self.app/'yolo11n-pose.pt').read_bytes(),b'keep model')
        self.assertEqual((self.app/'app.py').read_text(),'old=1')
    def test_missing_feed_keeps_install(self):
        self.assertEqual(check(self.app)['version'],'1.0.0')
    def test_bad_hash_keeps_previous_release(self):
        self.publish(); check(self.app)
        package=self.publish(release='1.2.0'); package.write_bytes(b'corrupt')
        result=check(self.app)
        self.assertEqual(result['version'],'1.1.0')
        self.assertIn('checksum',result['status'])
    def test_path_traversal_rejected(self):
        self.publish({'../outside.py':'x=1','targeting.py':'x=1','requirements.txt':'','README.md':''})
        result=check(self.app)
        self.assertEqual(result['version'],'1.0.0')
        self.assertFalse((self.app/'outside.py').exists())
    def test_invalid_python_rejected(self):
        self.publish({'app.py':'def invalid(','targeting.py':'x=1','requirements.txt':'','README.md':''})
        self.assertEqual(check(self.app)['version'],'1.0.0')
        self.assertFalse((self.app/'active-release.json').exists())
    def test_no_downgrade(self):
        self.publish(); check(self.app)
        self.publish(release='1.0.1')
        self.assertEqual(check(self.app)['version'],'1.1.0')
    def test_disabled(self):
        self.publish()
        (self.app/'update-source.json').write_text('{"enabled":false}')
        self.assertEqual(check(self.app)['status'],'Update checks disabled.')
    def test_github_package_is_pinned_to_version(self):
        from unittest.mock import patch
        package=self.publish()
        manifest=(self.feed/'manifest.json').read_bytes()
        (self.app/'update-source.json').write_text(json.dumps({'manifest':'https://github.com/Zitely/Hazmob-FPS-Cheat/releases/latest/download/manifest.json'}))
        calls=[]
        def fetch(source,limit):
            calls.append(source)
            return manifest if source.endswith('manifest.json') else package.read_bytes()
        with patch('updater.get_bytes',side_effect=fetch):
            self.assertEqual(check(self.app)['version'],'1.1.0')
        self.assertEqual(calls[1],'https://github.com/Zitely/Hazmob-FPS-Cheat/releases/download/v1.1.0/hazmob-1.1.0.zip')
if __name__=='__main__': unittest.main()
