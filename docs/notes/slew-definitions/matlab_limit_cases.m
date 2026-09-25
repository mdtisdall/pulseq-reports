% The construction checks of MATLAB Pulseq on the cases of LIMIT_CASES in
% slew_paths.py (the same events, built with MATLAB Pulseq). Run in GNU Octave by
% slew_paths.py. Writes limit_cases_matlab.json in OUT_DIR:
% {name: [accepted, message]}.

addpath(getenv('PULSEQ_MATLAB'));
out_dir = getenv('OUT_DIR');
sys = mr.opts('MaxGrad', 40, 'GradUnit', 'mT/m', 'MaxSlew', 100, 'SlewUnit', 'T/m/s');
mt = @(x) x * 1e-3 * sys.gamma;
ext = @(t_us, a_mt) mr.makeExtendedTrapezoid('x', sys, 'times', t_us * 1e-6, ...
                                             'amplitudes', mt(a_mt), 'skip_check', true);

cases = struct();

function result = attempt(f)
  try
    f();
    result = {true, ''};
  catch err
    result = {false, strtrim(strsplit(err.message, "\n"){1})};
  end
end

function seq = add_blocks(sys, varargin)
  seq = mr.Sequence(sys);
  for k = 1:numel(varargin)
    b = varargin{k};
    if iscell(b)
      seq.addBlock(b{:});
    else
      seq.addBlock(b);
    end
  end
end

cases.segment_at_100pct = attempt(@() add_blocks(sys, ext([0 100], [0 10]), ext([0 100], [10 0])));

cases.segment_at_120pct = attempt(@() add_blocks(sys, ext([0 100], [0 12]), ext([0 120], [12 0])));

cases.trap_explicit_rise_200pct = attempt(@() add_blocks(sys, ...
  mr.makeTrapezoid('x', sys, 'amplitude', mt(20), 'riseTime', 100e-6, ...
                   'flatTime', 100e-6, 'fallTime', 100e-6)));

step = 3.5 * sys.maxSlew * sys.gradRasterTime / 2;
w = [(1:8) * step, 9 * step, (8:-1:1) * step];
cases.arb_oversampled_350pct = attempt(@() add_blocks(sys, ...
  mr.makeArbitraryGrad('x', w, sys, 'oversampling', true, 'first', 0, 'last', 0)));

cases.junction_step_110pct = attempt(@() add_blocks(sys, ext([0 100], [0 9]), ...
                                                    ext([0 120], [10.1 0])));

cases.junction_step_opposite_signs = attempt(@() add_blocks(sys, ext([0 10], [0 -0.9]), ...
                                                            ext([0 10], [0.9 0])));

cases.end_nonzero_then_no_gradient = attempt(@() add_blocks(sys, ext([0 100], [0 9]), ...
                                                            mr.makeDelay(50e-6)));

cases.unaligned_end_negative = attempt(@() add_blocks(sys, ...
  {ext([0 200], [0 -18]), mr.makeDelay(300e-6)}));

cases.unaligned_end_positive = attempt(@() add_blocks(sys, ...
  {ext([0 200], [0 18]), mr.makeDelay(300e-6)}));

cases.zero_duration_block_in_joint = attempt(@() add_blocks(sys, ext([0 100], [0 9]), ...
  mr.makeLabel('SET', 'LIN', 0), ext([0 100], [9 0])));

fid = fopen(fullfile(out_dir, 'limit_cases_matlab.json'), 'w');
fprintf(fid, '%s', jsonencode(cases));
fclose(fid);
disp(jsonencode(cases));
