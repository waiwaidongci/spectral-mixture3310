<script setup lang="ts">
import {computed, ref, watch} from 'vue';
import {useRouter} from 'vue-router';
import {ArrowRight} from 'lucide-vue-next';
import {useResearchData} from '../hooks/useResearch';
import {useAuth} from '../stores/auth';
import {useAction} from '../hooks/useAction';
import {createRun} from '../api/runs';
import LibrarySelector from '../components/LibrarySelector.vue';
import Notice from '../components/common/Notice.vue';
import {BandExclusion} from '../types/domain';

const s = useResearchData(), auth = useAuth(), a = useAction(), router = useRouter();
const selected = ref(0), chosen = ref<number[]>([]), name = ref(''), sigma = ref(.005), repeats = ref(80), seed = ref(2026);
const excludedWaves = ref<Set<number>>(new Set());
const exclusionReasons = ref<Record<string, string>>({});
const library = computed(() => s.libraries.find(l => l.id === selected.value) || s.libraries[0]);
const wavelengths = computed(() => library.value?.wavelengths || []);
const retainedCount = computed(() => wavelengths.value.length - excludedWaves.value.size);
const missingReason = computed(() => [...excludedWaves.value].some(w => !(exclusionReasons.value[String(w)] || '').trim()));

watch(() => library.value?.id, async id => {
  if (id) {
    await s.loadLibrary(id);
    chosen.value = s.samples.slice(0, 3).map(x => x.id);
  }
  excludedWaves.value = new Set();
  exclusionReasons.value = {};
}, {immediate: true});

function toggleWave(w: number) {
  const next = new Set(excludedWaves.value);
  if (next.has(w)) { next.delete(w); delete exclusionReasons.value[String(w)]; }
  else next.add(w);
  excludedWaves.value = next;
}

function submit() {
  a.execute(async () => {
    const band_exclusions: BandExclusion[] = [...excludedWaves.value]
      .sort((x, y) => x - y)
      .map(w => ({wavelength: w, reason: exclusionReasons.value[String(w)].trim()}));
    const run = await createRun({name: name.value, library_id: library.value.id, sample_ids: chosen.value, noise_sigma: sigma.value, repeats: repeats.value, seed: seed.value, band_exclusions});
    router.push('/results?run=' + run.id);
  });
}
</script>

<template>
  <div class="page">
    <div class="page-title">
      <div>
        <p class="eyebrow">UNMIXING PROTOCOL / 03</p>
        <h1>解混配置<span>非负、和为一，与固定端元假设一起生效；污染波段按波长排除并冻结。</span></h1>
      </div>
    </div>
    <Notice :message="s.error||a.error.value" @retry="s.refresh"/>
    <div class="editor-grid">
      <form @submit.prevent="submit">
        <label>研究名称<input aria-label="研究名称" v-model="name" minlength="2" maxlength="120" required placeholder="例如：首批矿物三样本复配研究" :disabled="auth.user?.role==='viewer'"/></label>
        <LibrarySelector :libraries="s.libraries" :model-value="library?.id||0" @update:model-value="selected=$event"/>
        <div v-if="library&&!library.supported" class="notice">{{library.reason}}</div>
        <div class="form-heading"><span>01</span><h2>选择混合样本</h2></div>
        <div class="sample-selector">
          <label v-for="sample in s.samples" :key="sample.id"><input type="checkbox" :value="sample.id" v-model="chosen"/><span>{{sample.code}}<small>{{sample.name}}</small></span></label>
        </div>
        <p class="caption">已选{{chosen.length}}个；允许1–6个，样本数×重复数≤480。</p>
        <div class="form-heading"><span>02</span><h2>排除杂散光污染波段</h2></div>
        <p class="caption">勾选受杂散光污染的波长并逐波段填写原因。配比、噪声重拟合与残差判定只使用保留波段；被排除波段仍保留在全谱重建中并标注原因。规则随研究冻结，历史研究不改写。</p>
        <div class="band-exclusion-grid">
          <label v-for="w in wavelengths" :key="w" :class="['band-chip',{excluded:excludedWaves.has(w)}]">
            <input type="checkbox" :value="w" :checked="excludedWaves.has(w)" @change="toggleWave(w)"/>
            <span>{{w}} nm</span>
          </label>
        </div>
        <div v-for="w in [...excludedWaves].sort((x,y)=>x-y)" :key="w" class="band-reason-row">
          <label>{{w}} nm 污染原因<input :aria-label="w+'nm 污染原因'" v-model="exclusionReasons[String(w)]" minlength="2" maxlength="200" required placeholder="例如：探测器边缘杂散光"/></label>
        </div>
        <p class="caption" :class="{'warning-text':retainedCount<2}">保留 {{retainedCount}} / {{wavelengths.length}} 个波段；至少保留2个波段，且保留波段上增广矩阵仍须满列秩，否则拒绝计算。</p>
        <div class="form-heading"><span>03</span><h2>条件测量噪声</h2></div>
        <div class="form-row">
          <label>已知测量sigma<input aria-label="测量sigma" type="number" min="0" max=".2" step=".001" v-model.number="sigma"/></label>
          <label>条件重拟合次数<input aria-label="重拟合次数" type="number" min="20" max="120" v-model.number="repeats"/></label>
        </div>
        <label>根随机种子<input aria-label="随机种子" type="number" min="0" max="2147483647" v-model.number="seed"/></label>
        <p class="caption">以观测谱加独立Gaussian噪声，固定端元在保留波段重拟合。范围不包括端元误差，也不保证真实配比覆盖；sigma=0时扰动退化。</p>
        <button v-if="auth.user?.role!=='viewer'" class="primary" :disabled="a.busy.value||!library?.supported||chosen.length<1||chosen.length>6||chosen.length*repeats>480||retainedCount<2||missingReason">提交解混研究 <ArrowRight :size="16"/></button>
        <p v-else class="role-note">阅读者可查看配置，提交研究需要研究员权限。</p>
      </form>
      <aside class="method-note">
        <span class="eyebrow">METHOD NOTE / 01</span>
        <h2>先检查，<br/>再枚举支持集。</h2>
        <ol>
          <li><b>排除后再验可辨识性</b><p>增广[A_保留;1]需满列秩、条件数≤1e6。排除导致秩亏或病态时拒绝，不输出貌似唯一的配比。</p></li>
          <li><b>约束全局最小RSS</b><p>枚举非空支持集，解等式KKT并筛非负；结果再检查完整KKT，全部只在保留波段进行。</p></li>
          <li><b>全谱展示、范围有限</b><p>配比回乘完整端元矩阵展示全谱重建；Gaussian分位不是成分真值保证，高残差还可能来自模型失配。</p></li>
        </ol>
      </aside>
    </div>
  </div>
</template>
