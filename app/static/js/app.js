/* Job Search AI front-end — Alpine.js data component. */

function toDateInputValue(date) {
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 10);
}

function isoDateDaysAgo(days) {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() - days);
  return toDateInputValue(date);
}

function jobSearchApp() {
  return {
    // ---------- state ----------
    availableSources: [],
    todayIso: toDateInputValue(new Date()),
    form: {
      keywords: "",
      location: "Bengaluru, Hyderabad, Pune, Chennai",
      sources: [],
      // limit_per_source is no longer user-facing; the backend applies its own default.
      // Default cutoff: last 30 days (matches backend schema default).
      posted_after: isoDateDaysAgo(30),
      remote_only: false,
    },

    ai: { provider: "openai", api_key: "", model: "", feedback_loops: 10 },
    settingsOpen: false,

    loading: { search: false, resume: false, ats: false, upload: false },

    jobs: [],
    filterText: "",
    lastQuery: "",
    searchErrors: {},
    timings: {},
    searchProgress: {
      value: 0,
      label: "",
      timer: null,
    },

    selectedJob: null,

    resume: {
      filename: "",
      text: "",
      chars: 0,
      template_docx_base64: "",   // base64 of uploaded .docx bytes — reused as styling template
      is_docx_template: false,     // true when upload was a .docx we can template from
    },
    candidateNotes: "",
    jobDescription: "",

    resumeOutput: { markdown: "", docx_base64: "", filename: "", used_template: false },
    atsOutput: {
      score: null,
      matched_keywords: [],
      missing_keywords: [],
      strengths: [],
      gaps: [],
      recommendations: [],
      formatting_notes: [],
      scored_target: "",  // "tailored" | "uploaded" | ""
    },

    errorMsg: "",

    // ---------- lifecycle ----------
    async init() {
      try {
        const srcs = await fetch("/api/sources").then(r => r.json());
        this.availableSources = srcs.sources || [];
        this.form.sources = this.availableSources.map(s => s.key);
      } catch (err) {
        console.error("init failed", err);
      }
    },

    // ---------- helpers ----------
    get filteredJobs() {
      if (!this.filterText.trim()) return this.jobs;
      const q = this.filterText.toLowerCase();
      return this.jobs.filter(j =>
        (j.title || "").toLowerCase().includes(q) ||
        (j.company || "").toLowerCase().includes(q) ||
        (j.location || "").toLowerCase().includes(q) ||
        (j.source || "").toLowerCase().includes(q)
      );
    },

    scrollToPanel(id) {
      this.$nextTick(() => {
        const el = document.getElementById(id);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    },

    canTailor() {
      return !!(this.selectedJob && this.jobDescription.trim() &&
                (this.resume.text.trim() || this.candidateNotes.trim()));
    },
    canScore() {
      return !!(this.selectedJob && this.jobDescription.trim() && this.resume.text.trim());
    },

    scoreColor(s) {
      if (s === null || s === undefined) return "";
      if (s >= 80) return "is-success";
      if (s >= 60) return "is-warning";
      return "is-danger";
    },

    aiPayload() {
      return {
        provider: this.ai.provider || "openai",
        api_key: this.ai.api_key || null,
        model: this.ai.model || null,
      };
    },

    async copyText(text) {
      try { await navigator.clipboard.writeText(text || ""); }
      catch (_) { /* ignore */ }
    },

    startSearchProgress() {
      const steps = [
        { value: 14, label: "Preparing your search request..." },
        { value: 32, label: "Contacting job sources..." },
        { value: 54, label: "Collecting matching roles..." },
        { value: 72, label: "Merging and filtering results..." },
        { value: 88, label: "Finalizing results..." },
      ];
      let idx = 0;
      this.searchProgress.value = steps[0].value;
      this.searchProgress.label = steps[0].label;
      if (this.searchProgress.timer) clearInterval(this.searchProgress.timer);
      this.searchProgress.timer = setInterval(() => {
        if (!this.loading.search) return;
        idx = Math.min(idx + 1, steps.length - 1);
        this.searchProgress.value = steps[idx].value;
        this.searchProgress.label = steps[idx].label;
      }, 700);
    },

    finishSearchProgress(success = true) {
      if (this.searchProgress.timer) {
        clearInterval(this.searchProgress.timer);
        this.searchProgress.timer = null;
      }
      this.searchProgress.value = success ? 100 : 0;
      this.searchProgress.label = success ? "Search complete." : "";
    },

    // ---------- search ----------
    async runSearch() {
      if (!this.form.keywords.trim()) return;
      this.loading.search = true;
      this.errorMsg = "";
      this.searchErrors = {};
      this.jobs = [];
      this.timings = {};
      this.startSearchProgress();
      try {
        const resp = await fetch("/api/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.form),
        });
        if (!resp.ok) {
          const t = await resp.text();
          throw new Error(t || `HTTP ${resp.status}`);
        }
        const data = await resp.json();
        this.jobs = data.jobs || [];
        this.lastQuery = data.query || this.form.keywords;
        this.searchErrors = data.sources_errored || {};
        this.timings = data.timings_s || {};
        this.finishSearchProgress(true);
      } catch (err) {
        this.errorMsg = "Search failed: " + (err.message || err);
        this.finishSearchProgress(false);
      } finally {
        this.loading.search = false;
      }
    },

    // ---------- selection ----------
    selectJob(job) {
      this.selectedJob = job;
      // Pre-fill job description textarea with anything we already have
      this.jobDescription = job.description || this.jobDescription || "";
      // Clear prior outputs so the panel doesn't show stale data
      this.resumeOutput = { markdown: "", docx_base64: "", filename: "", used_template: false };
      this.atsOutput = {
        score: null, matched_keywords: [], missing_keywords: [],
        strengths: [], gaps: [], recommendations: [], formatting_notes: [],
        scored_target: "",
      };
    },

    // ---------- resume upload ----------
    async uploadResume(ev) {
      const f = ev.target.files && ev.target.files[0];
      if (!f) return;
      this.loading.upload = true;
      try {
        const fd = new FormData();
        fd.append("file", f, f.name);
        const resp = await fetch("/api/resume/parse", { method: "POST", body: fd });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        this.resume.filename = data.filename || f.name;
        this.resume.text = data.text || "";
        this.resume.chars = (data.text || "").length;
        this.resume.template_docx_base64 = data.template_docx_base64 || "";
        this.resume.is_docx_template = !!data.is_docx_template;
      } catch (err) {
        this.errorMsg = "Upload failed: " + (err.message || err);
      } finally {
        this.loading.upload = false;
      }
    },

    // ---------- resume generation ----------
    async tailorResume() {
      if (!this.canTailor()) return;
      this.loading.resume = true;
      this.errorMsg = "";
      try {
        const resp = await fetch("/api/resume/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ai: this.aiPayload(),
            job_title: this.selectedJob.title,
            company: this.selectedJob.company,
            job_description: this.jobDescription,
            current_resume_text: this.resume.text,
            candidate_profile: this.candidateNotes,
            feedback_loops: Number(this.ai.feedback_loops) || 10,
            // Re-use the uploaded .docx as a styling template when available.
            template_docx_base64: this.resume.template_docx_base64 || null,
          }),
        });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        this.resumeOutput.markdown = data.resume_markdown;
        this.resumeOutput.docx_base64 = data.docx_base64;
        this.resumeOutput.filename = data.filename;
        this.resumeOutput.used_template = !!data.used_template;
      } catch (err) {
        this.errorMsg = "Resume generation failed: " + (err.message || err);
      } finally {
        this.loading.resume = false;
      }
    },

    downloadResume() {
      if (!this.resumeOutput.docx_base64) return;
      const bin = atob(this.resumeOutput.docx_base64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const blob = new Blob(
        [bytes],
        { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = this.resumeOutput.filename || "resume.docx";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 500);
    },

    // ---------- ATS ----------
    async scoreATS() {
      if (!this.canScore()) return;
      this.loading.ats = true;
      this.errorMsg = "";
      try {
        // If we generated a tailored resume, score THAT (the typical use case).
        // Otherwise score the uploaded resume. Expose which one we used so the
        // UI can display it.
        const useTailored = !!this.resumeOutput.markdown;
        const resume_text = useTailored ? this.resumeOutput.markdown : this.resume.text;
        const scored_target = useTailored ? "tailored" : "uploaded";
        const resp = await fetch("/api/ats/score", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ai: this.aiPayload(),
            resume_text,
            job_description: this.jobDescription,
          }),
        });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        this.atsOutput = { ...data, scored_target };
      } catch (err) {
        this.errorMsg = "ATS scoring failed: " + (err.message || err);
      } finally {
        this.loading.ats = false;
      }
    },
  };
}
