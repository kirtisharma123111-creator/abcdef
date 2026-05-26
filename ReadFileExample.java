import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public class ReadFileExample {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java ReadFileExample <file-path>");
            System.exit(1);
        }

        Path filePath = Paths.get(args[0]);

        try (BufferedReader reader = Files.newBufferedReader(filePath, StandardCharsets.UTF_8)) {
            String line;

            while ((line = reader.readLine()) != null) {
                System.out.println(line);
            }
        } catch (IOException error) {
            System.err.println("Could not read file: " + error.getMessage());
            System.exit(1);
        }
    }
}
