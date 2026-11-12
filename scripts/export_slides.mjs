/** Export the reviewed Artifact Session snapshot through the bundled runtime.
 * Pass absolute artifact-tool and presentation skill paths as CLI arguments.
 * This also supports rebuilding directly from experiment results when no
 * session snapshot exists.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { buildDeck } from './build_slides.mjs';

const [artifactToolPath, skillDir, pythonExecutable] = process.argv.slice(2);
if(!artifactToolPath || !skillDir || !pythonExecutable) {
  throw new Error('Usage: node scripts/export_slides.mjs ARTIFACT_TOOL_MJS PRESENTATION_SKILL_DIR PYTHON_EXE');
}
// fileURLToPath correctly decodes Chinese paths on Windows.
const { fileURLToPath } = await import('node:url');
const workspace=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {Presentation,PresentationFile}=await import(pathToFileURL(artifactToolPath).href);
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(skillDir,'container_tools/artifact_tool_utils.mjs')).href);
const privateDir=path.join(workspace,'tmp','slides');
await fs.mkdir(privateDir,{recursive:true});
let presentation;
try {
  presentation=Presentation.load(JSON.parse(await fs.readFile(path.join(privateDir,'deck-proto.json'),'utf8')));
} catch(error) {
  if(error.code!=='ENOENT') throw error;
  const data={};
  for(const [key,file] of Object.entries({stats:'data_stats',results:'metrics',trials:'validation_trials',selection:'selection',manifest:'manifest'})) {
    data[key]=JSON.parse(await fs.readFile(path.join(workspace,'outputs/default',file+'.json'),'utf8'));
  }
  presentation=buildDeck(Presentation.create({slideSize:{width:1280,height:720}}),data);
}
for(const slide of presentation.slides.items) {
  for(const chart of slide.charts.items) applyPresentationChartFont(chart,{fontFamily:'Microsoft YaHei'});
}
const candidatePath=path.join(privateDir,'candidate.pptx');
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const finalPath=path.join(workspace,'deliverables','project_slides.pptx');
const result=await finalizePresentation({
  workspaceDir:workspace,candidatePath,finalPath,pythonExecutable,
  integrityValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',
    ...[2,4,5,6,10].flatMap(n=>['--require-native-table-slide',String(n)])],
  requiredNativeTableOwnerSlides:[2,4,5,6,10],requiredNativeChartOwnerSlides:[3,7,9],
  fontPolicy:{basis:'design',families:['Microsoft YaHei']},
  materializeLiteralChartWorkbooks:true,verifyArtifactToolImport:true,
  receiptPath:path.join(privateDir,'validation.json'),
});
console.log(JSON.stringify(result));
