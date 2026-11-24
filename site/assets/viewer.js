// Load the viewer on demand and reuse its canvas across examples.
let viewer;
let active;
let request = 0;

async function createViewer() {
  const [THREE, {GLTFLoader}, {DRACOLoader}, {OrbitControls}] = await Promise.all([
    import('three'),
    import('three/addons/loaders/GLTFLoader.js'),
    import('three/addons/loaders/DRACOLoader.js'),
    import('three/addons/controls/OrbitControls.js'),
  ]);
  const draco = new DRACOLoader().setDecoderPath(
    'https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/gltf/'
  );
  const loader = new GLTFLoader().setDRACOLoader(draco);
  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#ECEAE5');
  scene.add(new THREE.HemisphereLight('#ffffff', '#6f6a62', 0.9));
  const key = new THREE.DirectionalLight('#ffffff', 2.8);
  key.position.set(-2.5, 3, 0.8);
  scene.add(key);
  const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 1000);
  const controls = new OrbitControls(camera, renderer.domElement);
  const render = () => renderer.render(scene, camera);
  controls.addEventListener('change', render);

  const resize = new ResizeObserver(([entry]) => {
    const {width, height} = entry.contentRect;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    render();
  });
  let current;
  const models = new Map();
  return {
    async load(url) {
      if (!models.has(url)) {
        models.set(url, loader.loadAsync(url).then(result => result.scene).catch(error => {
          models.delete(url);
          throw error;
        }));
      }
      return models.get(url);
    },
    show(stage, model) {
      if (current) scene.remove(current);
      scene.add(current = model);
      stage.appendChild(renderer.domElement);
      resize.disconnect();
      resize.observe(stage);
      const bounds = new THREE.Box3().setFromObject(model);
      const radius = bounds.getSize(new THREE.Vector3()).length() / 2;
      const center = bounds.getCenter(new THREE.Vector3());
      const distance = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2));
      camera.near = distance / 100;
      camera.far = distance * 10;
      camera.updateProjectionMatrix();
      camera.position.copy(center).add(new THREE.Vector3(0.9, 0.55, 1).normalize().multiplyScalar(distance));
      controls.target.copy(center);
      controls.update();
    },
  };
}

async function open(button) {
  const stage = button.parentElement;
  const id = ++request;
  const status = stage.querySelector('.msg');
  button.disabled = true;
  status.textContent = 'Loading 3D model…';
  try {
    viewer ??= createViewer().catch(error => {
      viewer = undefined;
      throw error;
    });
    const view = await viewer;
    const model = await view.load(button.dataset.glb);
    if (id !== request) return;
    if (active) active.classList.remove('live');
    view.show(stage, model);
    stage.classList.add('live');
    active = stage;
  } catch (error) {
    if (id === request) status.textContent = 'The 3D view could not load. Try again.';
  } finally {
    if (status.textContent === 'Loading 3D model…') status.textContent = '';
    button.disabled = false;
  }
}

document.querySelectorAll('button[data-glb]').forEach(button => {
  button.addEventListener('click', () => open(button));
});
