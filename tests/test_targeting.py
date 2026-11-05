import sys,unittest,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from targeting import Detection,head_point,choose_head,movement,may_move
class HeadTests(unittest.TestCase):
    def setUp(self): self.box=Detection(50,50,150,250,.9)
    def test_two_confident_head_points(self):
        self.assertEqual(head_point([[90,75,.8],[110,75,.8]],self.box),(100,75))
    def test_no_box_fallback(self):
        self.assertIsNone(head_point([],self.box))
        self.assertIsNone(head_point([[90,75,.8]],self.box))
        self.assertIsNone(head_point([[90,75,.2],[110,75,.2]],self.box))
    def test_invalid_keypoints(self):
        self.assertIsNone(head_point([[float('nan'),75,.9],[0,0,.99],[100,240,.99]],self.box))
    def test_selection(self):
        self.assertEqual(choose_head([(None,self.box),((100,75),self.box)],(100,100),50)[1],(100,75))
        self.assertIsNone(choose_head([((100,75),self.box)],(500,500),100))
    def test_snap_no_twelve_pixel_cap(self):
        self.assertEqual(movement((100,0),(0,0),1,240,1),(100,0))
        self.assertLessEqual(math.hypot(*movement((500,500),(0,0),1,240,1)),241)
    def test_stop_focus_latency(self):
        self.assertTrue(may_move(True,True,True,True,.1,False))
        self.assertFalse(may_move(True,True,True,False,.1,False))
        self.assertFalse(may_move(True,True,True,True,.3,False))
        self.assertFalse(may_move(True,True,True,True,.1,True))
if __name__=='__main__': unittest.main()
