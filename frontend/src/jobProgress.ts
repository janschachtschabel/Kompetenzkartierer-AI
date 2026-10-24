// How far a job has come: the progress codes the page has words for (jobs.progress),
// each with the numbers its words need. tests/jobProgressCodes.test.ts holds them to
// the codes the backend's jobs report.
export const JOB_PROGRESS: Readonly<Record<string, readonly string[]>> = {
  // source.check (backend app/sources/check_job.py)
  checking: ["done", "total"],
  // source.convert (backend app/conversion/job.py)
  converting: [],
  // extract.run (backend app/pipeline/progress.py, ProgressCode)
  extract_profile: [],
  extract_outline: ["headings"],
  extract_segments: ["units"],
  extract_frame: [],
};
