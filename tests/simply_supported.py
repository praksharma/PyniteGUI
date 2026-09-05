from Pynite import FEModel3D
model = FEModel3D()

# User-defined material
material = "Steel_A992"
E = 29_000  # ksi
nu = 0.3
G = E / (2 * (1 + nu)) # ksi
rho = 0.49 / (12**3)   # kci

# Add material to model
model.add_material(name=material, E=E, G=G, nu=nu, rho=rho)

# Arbitrarily chosen wide-flange section
model.add_section("W18x35", A=10.3, Iy=15.3, Iz=510, J=0.506)

# Add nodes (35 ft span)
model.add_node('N0', 0, 0, 0)
model.add_node('N1', 35*12, 0, 0)

model.add_member(
    "M1",
    i_node="N0",
    j_node="N1",
    material_name="Steel_A992",
    section_name="W18x35",
    rotation=0,
    tension_only=False,
    comp_only=False
)

# Pin support
model.def_support(
    node_name="N0",
    support_DX=True,
    support_DY=True,
    support_DZ=True,
    support_RX=False,
    support_RY=False,
    support_RZ=False
)

# Roller support
model.def_support(
    node_name="N1",
    support_DX=False,
    support_DY=True,
    support_DZ=True,
    support_RX=True,  # For stability
    support_RY=False,
    support_RZ=False
)

# Distributed dead load
w_D = -0.120 / 12  # 0.12 klf to k/in

# Distributed live load
w_L =  -0.100 / 12  # 0.1 klf to k/in

# Add dead load
model.add_member_dist_load(
    member_name="M1",
    direction="Fy",
    w1=w_D,
    w2=w_D,
    x1=0,
    x2=35*12,  # 35 feet to inches
    case="D"
)

# Add live load
model.add_member_dist_load(
    member_name="M1",
    direction="Fy",
    w1=w_L,
    w2=w_L,
    x1=0,
    x2=35*12,  # 35 feet to inches
    case="L"
)

# self_weight = factor * member.material.rho * member.section.A

# Add self weight
model.add_member_self_weight(global_direction="FY", factor=-1, case='SW')

# Add load combinations
model.add_load_combo(
    name="D+L",
    factors={"SW": 1.0, "D": 1.0, "L": 1.0},
    combo_tags="Service"
)

model.add_load_combo(
    name="1.2D+1.6L",
    factors={"SW": 1.2, "D": 1.2, "L": 1.6},
    combo_tags="Strength"
)

model.add_load_combo(
    name="Dead",
    factors={"SW": 1.0, "D": 1.0},
    combo_tags="Dead"
)

model.add_load_combo(
    name="Live",
    factors={"L": 1},
    combo_tags="Live"
)

model.add_load_combo(
    name="Self Wt",
    factors={"SW": 1},
    combo_tags="Self Weight"
)

model.analyze_linear(log=True, check_stability=True, check_statics=True)

# Print reactions
print(f"Left Support Reaction: {model.nodes['N0'].RxnFY} kips")
print(f"Right Support Reaction: {model.nodes['N1'].RxnFY} kips")

# Print the max/min shears and moments in the beam
print(f"Maximum Factored Shear: {model.members['M1'].max_shear('Fy', '1.2D+1.6L')} kips")
print(f"Minimum Factored Shear: {model.members['M1'].min_shear('Fy', '1.2D+1.6L')} kip")
print()
print(f"Maximum Factored Moment: {model.members['M1'].max_moment('Mz', '1.2D+1.6L')/12} kip-ft")
print(f"Minimum Factored Moment: {model.members['M1'].min_moment('Mz', '1.2D+1.6L')/12} kip-ft")
print()
print(f"Maximum Moment Dead: {model.members['M1'].max_moment('Mz', 'Dead')/12} kip-ft")
print(f"Minimum Moment Dead: {model.members['M1'].min_moment('Mz', 'Dead')/12} kip-ft")
print()
print(f"Maximum Moment Live: {model.members['M1'].max_moment('Mz', 'Live')/12} kip-ft")
print(f"Minimum Moment Live: {model.members['M1'].min_moment('Mz', 'Live')/12} kip-ft")
print()

# Print the max/min deflections in the beam
print(f"Maximum Deflection: {model.members['M1'].max_deflection('dy', 'D+L')} in")
print(f"Minimum Deflection: {model.members['M1'].min_deflection('dy', 'D+L')} in")

model.members['M1'].plot_shear(Direction='Fy', combo_name='1.2D+1.6L', n_points=2)
model.members['M1'].plot_moment(Direction='Mz', combo_name='1.2D+1.6L', n_points=50)
model.members['M1'].plot_deflection('dy', combo_name='D+L', n_points=50)