% The MATLAB Pulseq half of scripts/rf_references.py: runs mr.simRf on the first RF
% block of a .seq file in GNU Octave, and writes the results to a JSON file.
%
% Environment variables:
%   MATLAB_PULSEQ  a checkout of github.com/pulseq/pulseq (the rf-references shell
%                  of flake.nix sets it to the pinned commit)
%   SEQ            the .seq file
%   OUT            the JSON file to write
%   GAMMA, B0      the gyromagnetic ratio (Hz/T) and B0 (T) of the sequence: mr.simRf
%                  reads them from mr.opts() for an RF event with a ppm offset, and a
%                  .seq file does not store them
%
% The JSON: {"octave", "dt", "f_hz", "mz", "mxy_re", "mxy_im", "ref_eff_re",
% "ref_eff_im", "resampled_re", "resampled_im"}. f_hz, mz and mxy are the outputs F,
% Mz_z and Mz_xy of mr.simRf, and ref_eff its refocusing efficiency. "resampled" is the
% RF that mr.simRf simulates (rad/s, one value for each step of dt): the lines of
% simRf.m that resample the RF, copied here because simRf.m does not return it.

addpath(fullfile(getenv('MATLAB_PULSEQ'), 'matlab'));
mr.opts('gamma', str2double(getenv('GAMMA')), 'B0', str2double(getenv('B0')), ...
        'setAsDefault', true);
% mr.simRf warns that it reads gamma and B0 from mr.opts() for a ppm offset: set above.
warning('off', 'all');

seq = mr.Sequence();
seq.read(getenv('SEQ'));
rf = [];
for i = 1:numel(seq.blockDurations)
  b = seq.getBlock(i);
  if ~isempty(b.rf)
    rf = b.rf;
    break;
  end
end
if isempty(rf)
  error('rf_references_simrf: the sequence has no RF block');
end

[Mz_z, Mz_xy, F, ref_eff] = mr.simRf(rf);

% A copy of the resampling of simRf.m: the time step from the bandwidth, the time
% axis T and the RF with its offsets, interpolated linearly at T.
[bw, f0] = mr.calcRfBandwidth(rf, 0.5, 10, 10e-6);
bw = abs(bw) + abs(f0);
dt = 10e-6;
if bw > 4e3
  dt = 5e-6;
  if bw > 1e4
    dt = 2e-6;
    if bw > 20000
      dt = 1e-6;
    end
  end
end
T = (1:round(rf.shape_dur/dt))*dt - 0.5*dt;
sys = mr.opts();
full_freq = rf.freqOffset + rf.freqPPM*1e-6*sys.gamma*sys.B0;
full_phase = rf.phaseOffset + rf.phasePPM*1e-6*sys.gamma*sys.B0;
shapea = interp1(rf.t, 2*pi*rf.signal.*exp(1i*(full_phase + 2*pi*full_freq*rf.t)), ...
                 T, 'linear', 0);

% JSON with 17 significant digits, so that each double is written exactly.
num = @(x) ['[' strjoin(arrayfun(@(v) sprintf('%.17g', v), x(:)', ...
                                 'UniformOutput', false), ',') ']'];
parts = {
  sprintf('"octave":"%s"', OCTAVE_VERSION)
  sprintf('"dt":%.17g', dt)
  ['"f_hz":' num(F)]
  ['"mz":' num(Mz_z)]
  ['"mxy_re":' num(real(Mz_xy))]
  ['"mxy_im":' num(imag(Mz_xy))]
  ['"ref_eff_re":' num(real(ref_eff))]
  ['"ref_eff_im":' num(imag(ref_eff))]
  ['"resampled_re":' num(real(shapea))]
  ['"resampled_im":' num(imag(shapea))]
};
fid = fopen(getenv('OUT'), 'w');
fprintf(fid, '{%s}', strjoin(parts', ','));
fclose(fid);
