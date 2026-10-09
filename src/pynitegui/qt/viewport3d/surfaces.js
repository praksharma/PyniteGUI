import * as THREE from 'three';

// Render four-node solver faces. Display triangles do not change connectivity.
export function drawSurfaces(data, group) {
  if (!data.surfaces?.length) return;
  const bounds = new THREE.Box3().setFromPoints(data.nodes.map(node => new THREE.Vector3(...node.position)));
  const centre = bounds.getCenter(new THREE.Vector3());
  const local = point => [point[0]-centre.x, point[1]-centre.y, point[2]-centre.z];
  const positions = data.nodes.flatMap(node => local(node.position));
  const triangles = [], edges = [], seen = new Set();
  for (const cell of data.surfaces) {
    triangles.push(cell[0], cell[1], cell[2], cell[0], cell[2], cell[3]);
    for (let i = 0; i < 4; i++) {
      const a = cell[i], b = cell[(i + 1) % 4], key = [Math.min(a,b), Math.max(a,b)].join(':');
      if (!seen.has(key)) {seen.add(key);edges.push(...local(data.nodes[a].position), ...local(data.nodes[b].position));}
    }
  }
  if (data.surfaceFill !== false) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setIndex(triangles);geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
      color: data.colors.accent, side: THREE.DoubleSide, roughness: .8,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
    }));
    mesh.position.copy(centre);mesh.userData.surfaceFaces = data.surfaces.length;group.add(mesh);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(edges, 3));
  const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({color:data.colors.member}));
  lines.position.copy(centre);group.add(lines);
}
