# GLB to MMD/VMD Rigging Notes

## Current Result

We have validated a first end-to-end path from a static Hunyuan3D GLB to a Blender-driven MMD/VMD animation output.

Current V0 path:

```text
Hunyuan3D static textured GLB
-> Blender 5.1.2 import
-> geometry inspection
-> coarse humanoid armature creation
-> coarse spatial vertex groups / weights
-> optional MMD-style Japanese bone names
-> MMD Tools VMD import
-> optional camera VMD import
-> optional WAV inserted into the .blend sequencer
-> .blend save
-> animated GLB export
-> browser GLB viewer playback
```

This proves that the pipeline is technically connected, but it does not yet produce production-quality dance animation.

## Verified Runtime

Blender:

```text
/home/team/zouzhiyuan/blender-5.1.2-linux-x64/blender
Blender 5.1.2
```

MCP:

```text
Codex MCP server: blender_lab
Blender bridge socket: 127.0.0.1:9876
```

MMD add-on:

```text
MMD Tools 4.5.12
Installed extension: /home/team/zouzhiyuan/.config/blender/5.1/extensions/user_default/mmd_tools
```

MMD Tools capabilities verified through MCP:

```text
mmd_tools_enabled: true
has_import_model: true
has_import_vmd: true
has_export_vmd: true
```

## Local Test Assets

Original Hunyuan3D GLB tested:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/hunyuan3d_white_hat_chibi_hq/white_hat_chibi_steps50_oct768_faces1m_textured.glb
```

Imported mesh facts:

```text
mesh_count: 1
armature_count: 0
vertices: 666116
polygons: 999998
materials: 1
images: 2 x 2048
shape_keys: false
vertex_groups: 0
```

This confirms the source asset is a static single mesh: no skeleton, no skinning weights, no expression morphs, and no MMD-compatible controls.

Downloaded Happy Hands test pack:

```text
/home/team/zouzhiyuan/image23D_Agent/assets/mmd_motions/learnmmd_happy_hands/HappyHandsMeme.zip
/home/team/zouzhiyuan/image23D_Agent/assets/mmd_motions/learnmmd_happy_hands/extracted/Happy Hands Meme.vmd
/home/team/zouzhiyuan/image23D_Agent/assets/mmd_motions/learnmmd_happy_hands/extracted/Happy Hands Meme Camera.vmd
/home/team/zouzhiyuan/image23D_Agent/assets/mmd_motions/learnmmd_happy_hands/extracted/Circus.wav
```

License/provenance note: the LearnMMD readme says the package was reconstructed from older downloads and the original source chain is imperfect. Treat this as local pipeline test material, not a default production/commercial asset.

## Generated Test Outputs

Programmatic body-motion MVP:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/white_hat_chibi_rigtest/white_hat_chibi_mvp_body_dance.blend
/home/team/zouzhiyuan/image23D_Agent/outputs/white_hat_chibi_rigtest/white_hat_chibi_mvp_body_dance_animated.glb
```

Viewer:

```text
http://10.2.16.106:8092/viewer?path=/home/team/zouzhiyuan/image23D_Agent/outputs/white_hat_chibi_rigtest/white_hat_chibi_mvp_body_dance_animated.glb
```

VMD test using MMD Tools sample VMD:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/white_hat_chibi_rigtest/white_hat_chibi_mvp_vmd_test.blend
/home/team/zouzhiyuan/image23D_Agent/outputs/white_hat_chibi_rigtest/white_hat_chibi_mvp_vmd_test_animated.glb
```

Happy Hands VMD + camera VMD + WAV:

```text
/home/team/zouzhiyuan/image23D_Agent/outputs/white_hat_chibi_rigtest/white_hat_chibi_happy_hands.blend
/home/team/zouzhiyuan/image23D_Agent/outputs/white_hat_chibi_rigtest/white_hat_chibi_happy_hands_animated.glb
```

Viewer:

```text
http://10.2.16.106:8092/viewer?path=/home/team/zouzhiyuan/image23D_Agent/outputs/white_hat_chibi_rigtest/white_hat_chibi_happy_hands_animated.glb
```

Happy Hands import status:

```text
body VMD: FINISHED
camera VMD: FINISHED
audio: inserted into .blend timeline
actions:
  Happy Hands Meme Camera_camera
  Happy Hands Meme Camera_camera_dis
  Happy Hands Meme_bone
frame range: 1-381
```

Animated GLB validation:

```text
MESH 3
ARMATURE 1
ACTIONS [('Happy Hands Meme Camera_camera', 7), ('Happy Hands Meme_bone', 130)]
```

## Helper Tools Added

Geometry inspection:

```text
tools/dump_glb_vertices.py
tools/plot_vertex_projections.py
```

The projection images are useful because Blender offscreen Workbench material rendering can be misleading for imported GLBs. Vertex projection gives a stable front/side/top silhouette independent of materials.

Rigging MVP:

```text
tools/rig_static_chibi_mvp.py
```

Important: this script is deliberately a proof-of-pipeline tool. It creates coarse armature and coarse spatial weights. It is not production auto-rigging.

GLB viewer update:

```text
tools/glb_viewer_server.py
```

The viewer now supports animated GLB autoplay and a Play/Pause animation button. GLB playback does not include audio; audio remains in `.blend` or must be added during video rendering/compositing.

## Observed Problems

The current animated result moves, but it is visibly wrong.

Observed issues:

- The hat, staff, book, hair, skirt, and body are all part of one dense mesh.
- Coarse weights pull rigid accessories and cloth-like parts with body bones.
- The model is not in a clean T-pose or A-pose.
- Limbs are chibi-proportioned and partially occluded by clothing/accessories.
- The skeleton is missing many MMD bones that real dance VMDs expect.
- There are no face shape keys, so VMD facial expressions have nothing to drive.
- There are no eye/mouth morphs, no finger bones, no foot IK, no toe bones, and no physics setup.
- The output animated GLB is large because the source mesh is approximately one million faces.

The screenshot symptom where the whole body appears to tremble or accessories deform is most likely caused by rough skeleton placement plus rough vertex weights, not by VMD import failure.

## Why V0 Works but Looks Bad

VMD files contain keyframes for named MMD bones and morphs. A static Hunyuan3D GLB has no such structure. The V0 bridge works by inventing a small approximate skeleton with MMD-style names:

```text
頭
上半身
下半身
左腕 / 左ひじ
右腕 / 右ひじ
左足 / 左ひざ
右足 / 右ひざ
```

Then it assigns vertices to those bones using simple spatial rules. This gives VMD something to drive, but it does not know semantic part boundaries. For example, a staff vertex near the left arm may become left-arm weighted even though the staff should mostly behave like a rigid accessory.

## Practical Quality Bar

For a true dance-quality result, the asset needs more than an armature:

- a more complete humanoid/MMD skeleton;
- better bone placement;
- skinning weights that separate body, clothing, hair, hat, staff, and book;
- rigid accessory parenting for staff/book/hat pieces when possible;
- IK controls for feet and hands;
- expression shape keys for eyes, mouth, brows, and smiles;
- optional cloth/hair physics or baked secondary motion;
- retargeting logic for chibi proportions.

Without these, VMD can technically import but the result will remain shaky or distorted.

## Recommended Next Steps

V1 should improve body animation quality before facial animation:

1. Create a lower-poly rig proxy from the high-poly GLB.
2. Segment or separate obvious accessories when possible: staff, book, hat, skirt, hair.
3. Add a more complete MMD-style skeleton with shoulder, wrist, ankle, toe, foot IK, and center/root bones.
4. Generate automatic weights on the proxy, then transfer weights to the high-poly mesh.
5. Parent rigid accessories to the nearest sensible bone instead of skinning them as deforming mesh.
6. Test with one short real VMD and one camera VMD.
7. Export both `.blend` and animated `.glb`.

V2 should add face/expression support:

1. Detect or manually define eye/mouth areas.
2. Add shape keys for blink, smile, mouth open, and basic vowels.
3. Map common VMD morph names to those shape keys.
4. Test expression VMD separately from body VMD.

V3 should target production output:

1. Render from Blender with camera VMD and WAV audio.
2. Export frame sequence or video.
3. Composite audio with rendered frames.
4. Keep browser GLB viewer for interactive geometry review, not final audio/video playback.

## Input Recommendations for Future Hunyuan3D Characters

If the final goal is animation, generate or choose images with:

- full body visible;
- arms and legs separated from torso;
- simple clear silhouette;
- minimal props crossing the body;
- T-pose or A-pose when possible;
- symmetric front-facing reference;
- no giant hat or staff blocking limb boundaries unless those parts can be segmented later.

Chibi characters can still work, but standard humanoid dance VMDs are made for human proportions. Expect retargeting and cleanup.

## Current Status

The GLB-to-MMD/VMD route is open at V0:

```text
static Hunyuan3D GLB -> generated armature/weights -> MMD Tools VMD import -> animated GLB
```

But the current quality is only suitable for pipeline validation. It should not be described as a finished dance animation system until V1 weight/rig improvements are implemented.
