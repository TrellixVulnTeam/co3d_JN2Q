import torch

from models.cox3d.modules.conv import ConvCo3d

torch.manual_seed(42)

T = S = 3
example_clip = torch.normal(mean=torch.zeros(4 * 3 * 3)).reshape((1, 1, 4, 3, 3))
next_example_frame = torch.normal(mean=torch.zeros(3 * 3)).reshape((1, 1, 3, 3))
next_example_clip = torch.stack(
    [
        example_clip[:, :, 1],
        example_clip[:, :, 2],
        example_clip[:, :, 3],
        next_example_frame,
    ],
    dim=2,
)
# Long example clip
long_example_clip = torch.normal(mean=torch.zeros(8 * 3 * 3)).reshape((1, 1, 8, 3, 3))
long_next_example_clip = torch.stack(
    [
        *[long_example_clip[:, :, i] for i in range(1, 8)],
        next_example_frame,
    ],
    dim=2,
)


def test_seperability():
    # Checks that the basic idea is sound

    # Take an example input and pass it thorugh a Conv3D the traditional way
    regular = torch.nn.Conv3d(
        in_channels=1, out_channels=1, kernel_size=(T, S, S), bias=True
    )

    regular_output = regular(example_clip).detach()

    # Take an example input and pass it thorugh a Conv3D the seperated way
    seperated = torch.nn.Conv3d(
        in_channels=1,
        out_channels=1,
        kernel_size=(T, S, S),
        bias=False,
        padding=(T - 1, 0, 0),
    )
    seperated.weight = regular.weight

    a = seperated(example_clip[:, :, 0, :, :].unsqueeze(2))[0, 0, :, 0, 0]
    b = seperated(example_clip[:, :, 1, :, :].unsqueeze(2))[0, 0, :, 0, 0]
    c = seperated(example_clip[:, :, 2, :, :].unsqueeze(2))[0, 0, :, 0, 0]
    d = seperated(example_clip[:, :, 3, :, :].unsqueeze(2))[0, 0, :, 0, 0]

    seperated_output = torch.tensor(
        [
            [
                [
                    [[c[0] + b[1] + a[2] + regular.bias]],
                    [[d[0] + c[1] + b[2] + regular.bias]],
                ]
            ]
        ]
    )

    assert torch.allclose(regular_output, seperated_output)


def test_basic_forward():
    conv = torch.nn.Conv3d(
        in_channels=1, out_channels=1, kernel_size=(T, S, S), bias=True
    )
    target = conv(example_clip)

    rconv = ConvCo3d.from_regular(conv)
    # rconv = ConvCo3d(
    #     in_channels=1,
    #     out_channels=1,
    #     kernel_size=(S, T, T),
    #     bias=True,
    #     temporal_fill="zeros",
    # )
    # rconv.conv.weight = conv.weight
    # rconv.bias = conv.bias

    _ = rconv(example_clip[:, :, 0])
    _ = rconv(example_clip[:, :, 1])
    x1 = rconv(example_clip[:, :, 2])
    x2 = rconv(example_clip[:, :, 3])
    output = torch.tensor([[[[[x1]], [[x2]]]]])

    output_alternative = rconv.forward_regular(example_clip)

    assert torch.allclose(output, output_alternative)
    assert torch.allclose(output, target)


def test_forward_long_kernel():
    conv = torch.nn.Conv3d(
        in_channels=1, out_channels=1, kernel_size=(T, S, S), bias=True
    )
    target = conv(example_clip)

    rconv = ConvCo3d.from_regular(conv)
    # rconv = ConvCo3d(
    #     in_channels=1,
    #     out_channels=1,
    #     kernel_size=(T, S, S),
    #     bias=True,
    #     temporal_fill="zeros",
    # )
    # rconv.weight = conv.weight
    # rconv.bias = conv.bias

    _ = rconv(example_clip[:, :, 0])
    _ = rconv(example_clip[:, :, 1])
    x1 = rconv(example_clip[:, :, 2])
    x2 = rconv(example_clip[:, :, 3])
    output = torch.tensor([[[[[x1]], [[x2]]]]])

    output_alternative = rconv.forward_regular(example_clip)

    assert torch.allclose(output, output_alternative)
    assert torch.allclose(output, target)


def test_from_conv3d():
    regular = torch.nn.Conv3d(
        in_channels=1, out_channels=1, kernel_size=(T, S, S), bias=True
    )
    target = regular(example_clip)

    rc3 = ConvCo3d.from_regular(regular)

    output = []
    for i in range(example_clip.shape[2]):
        output.append(rc3.forward(example_clip[:, :, i]))

    for t in range(example_clip.shape[2] - (T - 1)):
        assert torch.allclose(target[:, :, t], output[t + (T - 1)])

    # Alternative: gives same output as regular version
    output3 = rc3.forward_regular(example_clip)

    assert torch.allclose(output3, target)


def test_from_conv3d_bad_shape():
    regular = torch.nn.Conv3d(
        in_channels=1,
        out_channels=1,
        kernel_size=(T, S, S),
        bias=True,
        dilation=(2, 2, 2),
        padding=(1, 1, 1),
        stride=(2, 2, 2),
    )

    # Also warns
    rc3 = ConvCo3d.from_regular(regular)

    # Changed               V
    assert rc3.dilation == (1, 2, 2)
    assert rc3.stride == (1, 2, 2)

    # Not changed
    assert rc3.padding == (1, 1, 1)


example_clip_large = torch.normal(mean=torch.zeros(2 * 2 * 4 * 8 * 8)).reshape(
    (2, 2, 4, 8, 8)
)


def test_complex():
    # Take an example input and pass it thorugh a Conv3D the traditional way
    regular = torch.nn.Conv3d(
        in_channels=2,
        out_channels=4,
        kernel_size=(T, S, S),
        bias=True,
        groups=2,
        dilation=(1, 2, 2),
        stride=(1, 2, 2),
        padding=(2, 1, 1),
    )
    regular_output = regular(example_clip_large).detach()

    rc3 = ConvCo3d.from_regular(regular, temporal_fill="zeros")
    rc3_output = rc3.forward_regular(example_clip_large)

    assert torch.allclose(regular_output, rc3_output, atol=1e-7)


def test_forward_continuation():
    conv = torch.nn.Conv3d(
        in_channels=1,
        out_channels=1,
        kernel_size=(T, S, S),
        bias=True,
        padding=(1, 1, 1),
        padding_mode="zeros",
    )
    rconv = ConvCo3d.from_regular(conv, temporal_fill="zeros")

    # Run batch inference and fill memory
    target1 = conv(example_clip)
    output1 = rconv.forward_regular(example_clip)
    assert torch.allclose(target1, output1)

    # Next forward
    target2 = conv(next_example_clip)
    output2 = rconv.forward(next_example_frame)

    # Next-to-last frame matches
    assert torch.allclose(target2[:, :, -2], output2, atol=5e-8)

    # Passing in zeros gives same output
    output3 = rconv.forward(torch.zeros_like(next_example_frame), update_state=False)
    assert torch.allclose(target2[:, :, -1], output3, atol=5e-8)


def test_stacked_impulse_response():
    # An input has effect corresponding to the receptive field
    zeros = torch.zeros_like(next_example_frame)
    ones = torch.ones_like(next_example_frame)

    # Init regular
    conv1 = torch.nn.Conv3d(
        in_channels=1,
        out_channels=1,
        kernel_size=(5, S, S),
        bias=True,
        padding=(0, 1, 1),
        padding_mode="zeros",
    )
    conv2 = torch.nn.Conv3d(
        in_channels=1,
        out_channels=1,
        kernel_size=(3, S, S),
        bias=True,
        padding=(0, 1, 1),
        padding_mode="zeros",
    )

    # Init continual
    cnn = torch.nn.Sequential(
        ConvCo3d.from_regular(conv1, temporal_fill="zeros"),
        ConvCo3d.from_regular(conv2, temporal_fill="zeros"),
        ConvCo3d.from_regular(conv2, temporal_fill="zeros"),
    )

    cnn(ones)  # Impulse
    outputs = []
    for _ in range(15):
        outputs.append(cnn(zeros))

    same_as_last = [
        torch.equal(outputs[i], outputs[i - 1]) for i in range(1, len(outputs))
    ]

    # Correct result is output
    for i in range(len(same_as_last)):
        if i >= (5 - 1) + (3 - 1) + (3 - 1):
            assert same_as_last[i]
        else:
            assert not same_as_last[i]


def test_stacked_no_pad():
    # Without initialisation using forward_regular, the output has no delay

    # Init regular
    conv1 = torch.nn.Conv3d(
        in_channels=1,
        out_channels=1,
        kernel_size=(5, S, S),
        bias=True,
        padding=(0, 1, 1),
        padding_mode="zeros",
    )
    conv2 = torch.nn.Conv3d(
        in_channels=1,
        out_channels=1,
        kernel_size=(3, S, S),
        bias=True,
        padding=(0, 1, 1),
        padding_mode="zeros",
    )

    # Init continual
    rconv1 = ConvCo3d.from_regular(conv1, temporal_fill="zeros")
    rconv2 = ConvCo3d.from_regular(conv2, temporal_fill="zeros")

    # Targets
    target11 = conv1(long_example_clip)
    target12 = conv2(target11)

    target21 = conv1(long_next_example_clip)
    target22 = conv2(target21)

    # Test 3D mode
    output11 = rconv1.forward_regular(long_example_clip)
    output12 = rconv2.forward_regular(output11)
    torch.allclose(target12, output12, atol=5e-8)

    # Next 2D forward
    output21 = rconv1.forward(next_example_frame)
    output22 = rconv2.forward(output21)

    # Correct result is output
    assert torch.allclose(target22[:, :, -1], output22, atol=5e-8)
