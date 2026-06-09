# Adds the "video" service type and the OUTPUT_VIDEO media kind so the network
# can route text/image-to-video requests (e.g. LTX-2) and store the MP4 output.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0019_alter_inferencerequest_inference_type_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mediaasset",
            name="kind",
            field=models.CharField(
                choices=[
                    ("INPUT_AUDIO", "Input audio"),
                    ("OUTPUT_AUDIO", "Output audio"),
                    ("INPUT_IMAGE", "Input image"),
                    ("OUTPUT_IMAGE", "Output image"),
                    ("OUTPUT_MODEL", "Output 3D model"),
                    ("OUTPUT_VIDEO", "Output video"),
                ],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="providerservice",
            name="service_type",
            field=models.CharField(
                choices=[
                    ("llm", "Language model"),
                    ("stt", "Speech to text"),
                    ("tts", "Text to speech"),
                    ("image", "Image generation"),
                    ("mesh", "Image to 3D"),
                    ("music", "Music generation"),
                    ("video", "Video generation"),
                ],
                default="llm",
                max_length=16,
            ),
        ),
    ]
