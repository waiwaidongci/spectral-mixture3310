<script setup lang="ts">
import {computed, ref} from 'vue';
import {useRoute} from 'vue-router';
import {useResearchData} from '../hooks/useResearch';
import RunSummary from '../components/RunSummary.vue';
import SpectralPlot from '../components/SpectralPlot.vue';
import WeightsTable from '../components/WeightsTable.vue';
import DataTable from '../components/common/DataTable.vue';
import StatusBadge from '../components/common/StatusBadge.vue';
import Notice from '../components/common/Notice.vue';
import {number, scientific} from '../utils/format';
const s = useResearchData(true), route = useRoute(), selected = ref(Number(route.query.run) || 0), sampleId = ref(0);
const run = computed(() => s.runs.find(r => r.id === selected.value) || s.runs[0]);
const sample = computed(() => run.value?.result.samples?.find(x => x.sample_id === sampleId.value) || run.value?.result.samples?.[0]);
const reconstructed = computed(() => sample.value ? (sample.value.reconstructed_full || sample.value.point_fit.reconstructed) : []);
const residual = computed(() => sample.value ? (sample.value.residual_full || sample.value.point_fit.residual) : []);
const statusOf = (i: number) => sample.value?.band_status?.[i];
</script>

<template>
  <div class="page results-page">
    <div class="page-title">
      <div>
        <p class="eyebrow">COMPOSITION & RESIDUAL / 04</p>
        <h1>配比与残差<span>一份数值结果，保留它的可辨识性边界与波段排除档案。</span></h1>
      </div>
      <RouterLink class="outline" :to="'/notes'+(run?'?run='+run.id:'')">记录复配建议 →</RouterLink>
    </div>
    <Notice :message="s.error" @retry="s.refresh"/>
    <div class="run-picker">
      <label>解混档案<select aria-label="解混档案" :value="run?.id||''" @change="selected=Number(($event.target as HTMLSelectElement).value);sampleId=0"><option v-for="r in s.runs" :key="r.id" :value="r.id">#{{r.id}} / {{r.name}} / {{r.status}}</option></select></label>
      <StatusBadge v-if="run" :status="run.status"/>
    </div>
    <template v-if="run?.status==='completed'&&sample">
      <RunSummary :run="run"/>
      <div v-if="run.result.band_exclusions?.length" class="exclusion-banner">
        <b>已冻结排除规则（{{run.result.band_exclusions.length}} 波段，不参与配比/重拟合/残差判定）</b>
        <ul>
          <li v-for="ex in run.result.band_exclusions" :key="ex.wavelength">{{ex.wavelength}} nm —— {{ex.reason}}</li>
        </ul>
        <small>保留波段：{{run.result.retained_wavelengths?.map(w=>w+'nm').join('、')}}；规则与来源快照随本研究冻结，之后修改规则只会产生新研究。</small>
      </div>
      <label>当前混合样本<select aria-label="当前混合样本" v-model.number="sampleId"><option :value="0">{{run.result.samples[0].code}} / {{run.result.samples[0].name}}</option><option v-for="x in run.result.samples.slice(1)" :key="x.sample_id" :value="x.sample_id">{{x.code}} / {{x.name}}</option></select></label>
      <SpectralPlot :library="run.result.library" :endmembers="run.result.endmembers" :sample="sample"/>
      <div class="residual-summary">
        <div><span>RSS（保留波段）</span><b>{{scientific(sample.point_fit.rss)}}</b></div>
        <div><span>RMSE / 反射率（保留{{sample.retained_band_count ?? run.result.library.wavelengths.length}}波段）</span><b>{{number(sample.point_fit.rmse, 5)}}</b></div>
        <div><span>KKT活动误差</span><b>{{scientific(sample.point_fit.active_stationarity_error)}}</b></div>
        <strong :class="sample.high_residual?'warning':'supported'">{{sample.high_residual?'残差高于3σ参考，需查失配':'残差未超3σ参考，仍需复配验证'}}</strong>
      </div>
      <WeightsTable :endmembers="run.result.endmembers" :sample="sample"/>
      <p class="conditional-note">{{sample.interval_note}}</p>
      <div class="section-heading"><h2>全谱波段明细</h2><span>观测 − 约束重建（全谱展示；排除波段不参与拟合与判定）</span></div>
      <DataTable :head="['波长 / nm','波段状态','排除原因','观测反射率','重建反射率','残差']">
        <tr v-for="(wave,i) in run.result.library.wavelengths" :key="wave" :class="{'row-excluded':statusOf(i)&&!statusOf(i)!.retained}">
          <td>{{wave}}</td>
          <td><span :class="['band-state',statusOf(i)&&!statusOf(i)!.retained?'state-excluded':'state-retained']">{{statusOf(i)&&!statusOf(i)!.retained?'已排除':'保留'}}</span></td>
          <td class="note-cell">{{statusOf(i)?.exclusion_reason||'—'}}</td>
          <td>{{number(sample.observed[i],5)}}</td>
          <td>{{number(reconstructed[i],5)}}</td>
          <td>{{number(residual[i],5)}}</td>
        </tr>
      </DataTable>
      <div class="section-heading"><h2>条件重拟合抽样</h2><span>展示前10次，API保存全部{{sample.repeats}}次（保留波段加噪重拟合）</span></div>
      <DataTable :head="['重复',...run.result.endmembers.map(e=>e.name),'RSS']">
        <tr v-for="(w,j) in sample.replicate_weights.slice(0,10)" :key="j"><td>{{j+1}}</td><td v-for="(v,i) in w" :key="i">{{number(v,5)}}</td><td>{{scientific(sample.replicate_rss[j])}}</td></tr>
      </DataTable>
      <p class="caption">{{run.result.assumptions}}</p>
      <p class="fingerprint">算法版本 {{run.result.algorithm_version}} · 输入SHA256 {{run.result.input_hash}}</p>
    </template>
    <div v-else-if="run" class="pending">
      <h2>{{run.status==='failed'?'研究未能完成':'后台正在枚举支持集与条件重拟合'}}</h2>
      <p>{{run.error||'独立worker执行Python计算，本页每2秒更新。'}}</p>
    </div>
    <p v-else class="empty">尚无解混研究，请先选择可辨识光谱库。</p>
  </div>
</template>
