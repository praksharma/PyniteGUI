"""Isolated, fixed-schema OpenSees 3.8 RC evaluation worker; not an app backend."""
import hashlib
import importlib.metadata as metadata
import json
import math
import platform
import sys


def run(request):
    if not isinstance(request,dict) or set(request)-{'job','values','fibres','curvature'}:raise ValueError('Unknown request fields.')
    job=request.get('job')
    if job not in ('concrete','steel','section','member'):raise ValueError('Unknown evaluation job.')
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise ValueError('Assessment requires native macOS arm64.')
    if metadata.version('openseespymac')!='3.8.0.0':raise ValueError('Pinned native package required.')
    import openseespy.opensees as ops
    if metadata.version('openseespy')!='3.8.0.0' or ops.version()!='3.8.0':raise ValueError('Pinned OpenSeesPy 3.8.0.0 / engine 3.8.0 required.')
    ops.wipe();ops.model('basic','-ndm',2,'-ndf',3)
    ops.uniaxialMaterial('Concrete01',1,-4.,-.002,-1.,-.006)
    ops.uniaxialMaterial('Steel01',2,60.,29000.,.01)
    rows=[]
    if job in ('concrete','steel'):
        values=request.get('values')
        if not isinstance(values,list) or not 1<=len(values)<=256 or any(type(v) not in (float,int) or not math.isfinite(v) or abs(v)>.02 for v in values):raise ValueError('Bounded finite strain list required.')
        ops.testUniaxialMaterial(1 if job=='concrete' else 2)
        for value in values:
            ops.setStrain(value);rows.append(dict(strain=value,stress=ops.getStress(),tangent=ops.getTangent()))
    else:
        fibres=request.get('fibres');curvature=request.get('curvature')
        if not isinstance(fibres,list) or not 1<=len(fibres)<=512:raise ValueError('Bounded fibre list required.')
        if type(curvature) not in (float,int) or not math.isfinite(curvature) or not 0<curvature<=.0004:raise ValueError('Positive bounded curvature required.')
        ops.section('Fiber',1)
        for fibre in fibres:
            if not isinstance(fibre,list) or len(fibre)!=3:raise ValueError('Invalid fibre.')
            area,y,kind=fibre
            if type(area) not in (float,int) or type(y) not in (float,int) or not math.isfinite(area+y) or area<=0 or abs(y)>100 or kind not in ('concrete','steel'):raise ValueError('Invalid fibre data.')
            ops.fiber(y,0.,area,1 if kind=='concrete' else 2)
        length=120. if job=='member' else 0.
        ops.node(1,0.,0.);ops.node(2,length,0.);ops.fix(1,1,1,1)
        if job=='section':ops.fix(2,0,1,0);ops.element('zeroLengthSection',1,1,2,1)
        else:
            ops.geomTransf('Linear',1);ops.beamIntegration('Lobatto',1,1,5)
            ops.element('forceBeamColumn',1,1,2,1,1,'-iter',50,1e-12)
        ops.timeSeries('Linear',1);ops.pattern('Plain',1,1)
        ops.load(2,0.,0.,1.)
        ops.constraints('Transformation');ops.numberer('Plain');ops.system('BandGeneral')
        ops.test('NormUnbalance',1e-9,100);ops.algorithm('Newton');ops.integrator('DisplacementControl',2,3,curvature*(length if job=='member' else 1.));ops.analysis('Static')
        status=ops.analyze(1)
        if status!=0:raise ValueError(f'OpenSees analysis failed with code {status}.')
        ops.reactions()
        rows.append(dict(displacement=ops.nodeDisp(2),reaction=ops.nodeReaction(1),
            element_forces=ops.eleForce(1),section_forces=ops.eleResponse(1,'section',*( [3] if job=='member' else []),'force'),
            all_section_forces=([v for i in range(1,6) for v in ops.eleResponse(1,'section',i,'force')] if job=='member' else ops.eleResponse(1,'section','force'))))
    for row in rows:
        for value in row.values():
            values=value if isinstance(value,list) else [value]
            if any(not math.isfinite(v) for v in values):raise ValueError('Nonfinite engine response.')
    licences={}
    for name in ('openseespy','openseespymac'):
        try:d=metadata.distribution(name)
        except metadata.PackageNotFoundError:continue
        for path in d.files or ():
            if str(path).endswith('/LICENSE.md'):
                licences[name]=dict(version=d.version,sha256=hashlib.sha256(d.locate_file(path).read_bytes()).hexdigest())
    return dict(job=job,engine=ops.version(),package=metadata.version('openseespy'),python=platform.python_version(),
        platform=platform.platform(),machine=platform.machine(),licences=licences,rows=rows,production_ready=False)


if __name__=='__main__':
    try:
        raw=sys.stdin.read(1000000)
        result=run(json.loads(raw));print(json.dumps(result,allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error':str(exc)}));raise SystemExit(2)
