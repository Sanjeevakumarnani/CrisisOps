from app.models import OperationalEventCreate, ResponsePlanInput
from app.utils import pipe_list, event_to_memory

def test_pipe_list():
    assert pipe_list('water | shelter|| food') == ['water','shelter','food']

def test_event_model():
    e=OperationalEventCreate(title='Flooded ward',location='Demo',lat=17.4,lon=78.4)
    assert e.urgency == 'medium'

def test_plan_model():
    p=ResponsePlanInput(objective='Reach shelter',locations=['Demo'])
    assert p.locations == ['Demo']
