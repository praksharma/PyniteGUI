"""Explicit modal table conventions; no static force/reaction interpretation."""
from .modal import DOFS


def modal_table(result,units,kind='frequencies',mode=1):
    if kind=='frequencies':
        return ['Mode','Frequency (Hz)','Period (s)','Reference','Eigen residual'],[
            [i+1,float(f),float(1/f),result.normalization[i],float(result.residuals[i])] for i,f in enumerate(result.frequencies)]
    if kind=='mass_sources':
        return ['Source','Case','Generated self-weight',f'Weight ({units.force})',f'Mass ({units.force} s²/{units.length})'],[
            [row['load'],row['case'],'Yes' if row['generated_self_weight'] else 'No',units.to_display(row['weight'],'force'),
             row['weight']/result.settings.gravity*units.force_factor/units.length_factor] for row in result.source]
    if kind!='shapes':raise ValueError('Choose frequencies, shapes or mass_sources.')
    if type(mode) is not int or not 1<=mode<=len(result.frequencies):raise ValueError('Choose a solved mode number.')
    rotation=result.normalization[mode-1]=='rotation'
    headers=['Node',*(f'{dof} ({units.length}/rad)' if rotation else f'{dof} (ratio)' for dof in DOFS[:3]),
             *(f'{dof} (ratio)' if rotation else f'{dof} (rad/{units.length})' for dof in DOFS[3:])]
    rows=[]
    for name,shape in zip(result.project.nodes,result.shapes[mode-1]):
        rows.append([name,*(float(v)*units.length_factor if rotation else float(v) for v in shape[:3]),
                     *(float(v) if rotation else float(v)/units.length_factor for v in shape[3:])])
    return headers,rows
