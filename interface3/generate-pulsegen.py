BIT_RATE = 2_358_700

words = (0b0101010101_000111_01_10101010_010110, 0b011001_01101111_000000000000000000)
input_pattern_length = 32 + 14
output_pattern_length = 512
output_pattern_bits = output_pattern_length // input_pattern_length * input_pattern_length
output_pattern_freq = 50_000_000

bits = []
time = 0.0
for word in words:
    for bit in range(31, -1, -1):
        time = time + (1 / BIT_RATE) / 2
        bits.append((time, 0 if word & (1 << bit) == 0 else 1))

print("Time (s),RX")
time = 0
for bit in range(output_pattern_bits):
    if time > bits[0][0]:
        bits = bits[1:]
    print("%e,%d" % (time, bits[0][1]))
    time = time + 1/output_pattern_freq
