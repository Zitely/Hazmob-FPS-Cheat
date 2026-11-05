import unittest,sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from targeting import Detection,StableLock,SettlingController

def candidate(x,y=100):
    return ((x,y),Detection(x-20,y-20,x+20,y+100,.9))

class LockTests(unittest.TestCase):
    def test_requires_three_frames(self):
        lock=StableLock()
        self.assertIsNone(lock.update([candidate(130)],(100,100),190,1))
        self.assertIsNone(lock.update([candidate(130)],(100,100),190,1.05))
        self.assertEqual(lock.update([candidate(130)],(100,100),190,1.10)[1],(130,100))
    def test_does_not_jump_to_new_nearer_player(self):
        lock=StableLock()
        for now in (1,1.05,1.10): lock.update([candidate(150)],(100,100),190,now)
        selected=lock.update([candidate(105),candidate(151)],(100,100),190,1.15)
        self.assertEqual(selected[1],(151,100))
    def test_disappeared_target_never_uses_old_coordinates(self):
        lock=StableLock()
        for now in (1,1.05,1.10): lock.update([candidate(150)],(100,100),190,now)
        self.assertIsNone(lock.update([candidate(80)],(100,100),190,1.15))
        self.assertIsNone(lock.update([candidate(80)],(100,100),190,1.35))
        self.assertIsNone(lock.update([candidate(80)],(100,100),190,1.40))
        self.assertIsNone(lock.box)
    def test_ambiguous_match_does_not_move(self):
        lock=StableLock()
        for now in (1,1.05,1.10): lock.update([candidate(150)],(100,100),190,now)
        self.assertIsNone(lock.update([candidate(149),candidate(151)],(100,100),190,1.15))
    def test_empty_or_outside_fov(self):
        lock=StableLock()
        self.assertIsNone(lock.update([candidate(900)],(100,100),190,1))
        self.assertIsNone(lock.update([],(100,100),190,1.1))

class ControllerTests(unittest.TestCase):
    def test_no_large_jumps(self):
        control=SettlingController()
        delta=control.step((2000,2000),(0,0),1)
        self.assertLessEqual(math.hypot(*delta),24.8)
    def test_small_errors_stay_still(self):
        self.assertEqual(SettlingController().step((103,102),(100,100),1),(0,0))
    def test_overshoot_reduces_gain(self):
        control=SettlingController()
        control.step((100,0),(0,0),1)
        gain=control.gains[0]
        control.step((-50,0),(0,0),1.1)
        self.assertLess(control.gains[0],gain)
    def test_simulated_high_sensitivity_converges(self):
        control=SettlingController(); error=150
        for i in range(50):
            dx,_=control.step((error,0),(0,0),1+i*.05)
            error-=dx*12
        self.assertLessEqual(abs(error),8)
    def test_repeated_tick_does_not_double_move(self):
        control=SettlingController()
        control.step((100,0),(0,0),1)
        self.assertEqual(control.step((100,0),(0,0),1.005),(0,0))

if __name__=='__main__': unittest.main()
