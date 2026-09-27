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


def test_source_type_defaults_to_operator_and_supports_synthetic():
    operator = OperationalEventCreate(title='Operator report', location='Demo', lat=17.4, lon=78.4)
    synthetic = OperationalEventCreate(title='Demo report', location='Demo', lat=17.4, lon=78.4, source_type='synthetic')
    assert operator.source_type == 'operator'
    assert synthetic.source_type == 'synthetic'
